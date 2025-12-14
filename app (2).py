import streamlit as st
import numpy as np
import pandas as pd
import os
import glob
import plotly.express as px
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import mm
from io import BytesIO

# --- 1. 設定 ---
st.set_page_config(page_title="お家づくりのための簡易資金計画 Ver.21", layout="wide")
FONT_FILE = "ipaexg.ttf"

def get_plan_image_path(price):
    candidates = [f"plan_{price}.jpg", f"plan_{price}.png"]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

C_HEADER_BLUE = colors.HexColor("#6a5acd")
C_GREEN_HEAD = colors.HexColor("#66cdaa")
C_GREEN_BODY = colors.HexColor("#e0ffff")
C_PURPLE_HEAD = colors.HexColor("#9370db")
C_PURPLE_BODY = colors.HexColor("#e6e6fa")
C_ORANGE_HEAD = colors.HexColor("#ffa07a")
C_ORANGE_BODY = colors.HexColor("#ffdab9")
C_TEXT_GRAY = colors.HexColor("#555555")

def setup_japanese_font():
    try:
        pdfmetrics.registerFont(TTFont('IPAexGothic', FONT_FILE))
        return True
    except:
        return False

# --- 2. サイドバー入力 ---
st.sidebar.header("📝 営業用入力フォーム")
with st.sidebar.expander("👤 お客様情報", expanded=True):
    customer_name = st.text_input("お名前（様は自動付与）", "", placeholder="例：山田")
    income_man = st.number_input("世帯年収 (万円)", 200, 5000, 600, 10)
    own_money_man = st.number_input("自己資金/頭金 (万円)", 0, 5000, 200, 10)

with st.sidebar.expander("⚙️ 資金計画条件", expanded=True):
    calc_interest_rate = st.number_input("審査金利 (%)", 0.1, 5.0, 1.5, 0.1)
    calc_term_years = st.number_input("返済期間 (年)", 1, 50, 35, 1)

with st.sidebar.expander("🏗 予算シミュレーション設定", expanded=True):
    land_price_fixed = st.number_input("土地価格 (万円)", value=1500, step=50)
    
    st.caption("建物価格設定")
    b_price_1 = st.number_input("🟢 堅実プラン：建物", value=2000, step=50)
    b_price_2 = st.number_input("🟣 標準プラン：建物", value=2500, step=50)
    b_price_3 = st.number_input("🟠 充実プラン：建物", value=3000, step=50)

    st.caption("諸費用の自動計算")
    fee_rate_percent = st.number_input("諸費用率 (%)", value=7.0, step=0.5, help="標準プラン総額に対する諸費用の割合")
    
    std_total_temp = land_price_fixed + b_price_2
    fees_std_man = std_total_temp * (fee_rate_percent / 100)
    st.info(f"標準プランの諸費用目安：\n**約 {fees_std_man:.0f} 万円**")

with st.sidebar.expander("💰 住宅ローン控除設定", expanded=True):
    tax_rate = st.number_input("控除率 (%)", 0.1, 1.0, 0.7, 0.1)
    tax_years = st.number_input("控除期間 (年)", 1, 20, 13, 1)
    tax_limit = st.number_input("借入限度額 (万円)", 0, 10000, 4500, 100)

# --- 3. 計算ロジック ---
PLANS = {
    "堅実プラン": {"build": b_price_1, "color": C_GREEN_HEAD, "color_b": C_GREEN_BODY, "emoji": "🟢"},
    "標準プラン": {"build": b_price_2, "color": C_PURPLE_HEAD, "color_b": C_PURPLE_BODY, "emoji": "🟣"},
    "充実プラン": {"build": b_price_3, "color": C_ORANGE_HEAD, "color_b": C_ORANGE_BODY, "emoji": "🟠"}
}

def calculate_simulation(land_man, build_man, own_man, base_fees_man, std_build_man, rate, term):
    land = land_man * 10000
    building = build_man * 10000
    own_money = own_man * 10000
    
    diff_man = build_man - std_build_man
    variable_fee = diff_man * 0.03 # 3%変動
    fees = (base_fees_man + variable_fee) * 10000
    
    total_budget = land + building + fees
    loan = total_budget - own_money
    if loan < 0: loan = 0
    
    rate_monthly = (rate / 100) / 12
    num_payments = term * 12
    if loan > 0:
        payment = loan * rate_monthly / (1 - (1 + rate_monthly) ** -num_payments)
    else:
        payment = 0
    return {
        "total": total_budget, "loan": loan, "fees": fees, "land": land, "building": building,
        "payment": payment, "rate": rate, "term": term
    }

results = {}
for name, conf in PLANS.items():
    results[name] = calculate_simulation(
        land_price_fixed, conf["build"], own_money_man, 
        fees_std_man, b_price_2, 
        calc_interest_rate, calc_term_years
    )

def calculate_tax_deduction(loan_amount, rate, years, limit, tax_rate_val):
    balance = loan_amount
    deductions = []
    monthly_rate = (rate / 100) / 12
    payment = loan_amount * monthly_rate / (1 - (1 + monthly_rate) ** -(calc_term_years * 12))
    total_return = 0
    for y in range(1, years + 1):
        interest_year = balance * (rate/100)
        principal_year = (payment * 12) - interest_year
        balance -= principal_year
        if balance < 0: balance = 0
        target_balance = min(balance, limit * 10000)
        deduction = target_balance * (tax_rate_val / 100)
        deductions.append(deduction)
        total_return += deduction
    return total_return, deductions

std_loan = results["標準プラン"]["loan"]
tax_total, tax_yearly = calculate_tax_deduction(std_loan, calc_interest_rate, tax_years, tax_limit, tax_rate)
tax_monthly_equiv = tax_total / (tax_years * 12)

# --- 4. 画面表示 ---
st.title("🏡 お家づくりのための簡易資金計画 Ver.21")
tab1, tab2 = st.tabs(["📊 資金計画", "💰 減税シミュレーション"])

with tab1:
    st.markdown("土地価格を固定し、建物価格の違いによる3つの資金計画をシミュレーションします。")
    cols = st.columns(3)
    for i, (name, conf) in enumerate(PLANS.items()):
        r = results[name]
        with cols[i]:
            st.subheader(f"{conf['emoji']} {name}")
            st.metric("総予算", f"{r['total']/10000:,.0f} 万円")
            st.metric("月々支払", f"{r['payment']:,.0f} 円")
            df_pie = pd.DataFrame({"項目": ["建物", "土地", "諸費用"], "金額": [r['building'], r['land'], r['fees']]})
            fig = px.pie(df_pie, values='金額', names='項目', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=150, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.subheader("住宅ローン控除シミュレーション")
    col_t1, col_t2 = st.columns(2)
    col_t1.metric("13年間の還付総額", f"{tax_total:,.0f} 円")
    real_payment = results["標準プラン"]["payment"] - tax_monthly_equiv
    col_t2.metric("実質的な月々負担額", f"{real_payment:,.0f} 円", delta=f"-{tax_monthly_equiv:,.0f} 円 (相当)")
    df_tax = pd.DataFrame({"年数": [f"{i}年目" for i in range(1, tax_years + 1)], "還付額": [t/10000 for t in tax_yearly]})
    fig_tax = px.bar(df_tax, x="年数", y="還付額", title="毎年の還付金推移（概算）", color_discrete_sequence=["#9370db"])
    fig_tax.update_yaxes(title="還付額（万円）", tickformat=".1f")
    st.plotly_chart(fig_tax, use_container_width=True)

# --- 5. PDF出力機能 ---
def create_merged_pdf(c_name, income, res_data, land_fixed, t_total, t_limit, t_rate, t_years, plot_fig):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    font_name = "IPAexGothic"
    
    # === 1ページ目 ===
    p.setFillColor(C_HEADER_BLUE)
    p.rect(0, height - 30*mm, width, 30*mm, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont(font_name, 24)
    p.drawCentredString(width/2, height - 20*mm, "あなたの資金プラン")
    
    styles = getSampleStyleSheet()
    style_ja = ParagraphStyle(name='Japanese', parent=styles['Normal'], fontName=font_name, fontSize=12, leading=16)
    
    # ★変更点：「探していきましょう！」に文言修正
    txt = f"{c_name}様の世帯年収{income}万円と、ご検討中の土地価格({land_fixed}万円)を基に、建物グレード別の3つの資金計画をご提案します。<br/>ご希望のライフスタイルに合わせて、最適なプランを探していきましょう！"
    
    para = Paragraph(txt, style_ja)
    w, h = para.wrap(width - 60*mm, 50*mm)
    para.drawOn(p, 30*mm, height - 35*mm - h)
    
    p_names = ["堅実プラン", "標準プラン", "充実プラン"]
    rows = [["項目"] + p_names]
    rows.append(["総額"] + [f"{res_data[n]['total']/10000:,.0f}万円" for n in p_names])
    rows.append(["土地計画"] + [f"{res_data[n]['land']/10000:,.0f}万円" for n in p_names])
    rows.append(["建物価格"] + [f"{res_data[n]['building']/10000:,.0f}万円" for n in p_names])
    rows.append(["諸費用"] + [f"{res_data[n]['fees']/10000:,.0f}万円" for n in p_names])
    rows.append(["借入額"] + [f"{res_data[n]['loan']/10000:,.0f}万円" for n in p_names])
    rows.append(["金利/期間"] + [f"{res_data[n]['rate']:.1f}% / {res_data[n]['term']}年" for n in p_names])
    
    col_widths = [40*mm, 50*mm, 50*mm, 50*mm]
    t = Table(rows, colWidths=col_widths, rowHeights=12*mm)
    
    t.setStyle(TableStyle([
        ('FONT', (0,0), (-1,-1), font_name, 12), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 1, colors.white), ('TEXTCOLOR', (0,0), (0,-1), colors.white),
        ('BACKGROUND', (0,0), (0,-1), colors.grey),
        ('BACKGROUND', (1,0), (1,0), PLANS["堅実プラン"]["color"]), ('BACKGROUND', (1,1), (1,-1), PLANS["堅実プラン"]["color_b"]),
        ('TEXTCOLOR', (1,0), (1,0), colors.white),
        ('BACKGROUND', (2,0), (2,0), PLANS["標準プラン"]["color"]), ('BACKGROUND', (2,1), (2,-1), PLANS["標準プラン"]["color_b"]),
        ('TEXTCOLOR', (2,0), (2,0), colors.white),
        ('BACKGROUND', (3,0), (3,0), PLANS["充実プラン"]["color"]), ('BACKGROUND', (3,1), (3,-1), PLANS["充実プラン"]["color_b"]),
        ('TEXTCOLOR', (3,0), (3,0), colors.white), ('FONTNAME', (0,1), (-1,1), font_name), ('FONTSIZE', (1,1), (-1,1), 14),
    ]))
    t.wrapOn(p, width, height)
    t.drawOn(p, (width - 190*mm)/2, height - 35*mm - h - 15*mm - len(rows)*12*mm)
    
    y_pay = height - 35*mm - h - 15*mm - len(rows)*12*mm - 20*mm
    p.setFillColor(C_HEADER_BLUE)
    p.setFont(font_name, 18)
    p.drawCentredString(width/2, y_pay, "毎月の支払額目安")
    
    box_y = y_pay - 35*mm
    margin_x = (width - 150*mm)/4
    for i, n in enumerate(p_names):
        x = margin_x + (50*mm + margin_x)*i
        p.setFillColor(PLANS[n]["color"])
        p.rect(x, box_y + 20*mm, 50*mm, 10*mm, fill=1, stroke=0)
        p.setFillColor(colors.white)
        p.setFont(font_name, 12)
        p.drawCentredString(x + 25*mm, box_y + 23*mm, n)
        p.setFillColor(PLANS[n]["color_b"])
        p.rect(x, box_y, 50*mm, 20*mm, fill=1, stroke=0)
        p.setFillColor(colors.black)
        p.setFont(font_name, 16)
        p.drawCentredString(x + 25*mm, box_y + 8*mm, f"{res_data[n]['payment']:,.0f}円")

    p.setFillColor(C_TEXT_GRAY)
    p.setFont(font_name, 9)
    r_d = f"{res_data['標準プラン']['rate']:.1f}"
    p.drawString(20*mm, box_y - 15*mm, f"※諸費用は概算です。金利{r_d}%、期間{res_data['標準プラン']['term']}年で試算しています。")
    p.showPage()
    
    # === 2ページ目 ===
    p.setFillColor(C_HEADER_BLUE)
    p.rect(0, height - 30*mm, width, 30*mm, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont(font_name, 24)
    p.drawCentredString(width/2, height - 20*mm, "住宅ローン控除シミュレーション")
    
    p.setFillColor(colors.black)
    p.setFont(font_name, 12)
    p.drawString(20*mm, height - 45*mm, f"{c_name}様の「標準プラン」における住宅ローン減税（還付金）の目安を試算しました。")
    
    box_top = height - 60*mm
    box_h = 35*mm
    p.setStrokeColor(C_HEADER_BLUE)
    p.setLineWidth(2)
    p.rect(20*mm, box_top - box_h, width - 40*mm, box_h, stroke=1, fill=0)
    
    p.setFont(font_name, 16)
    p.drawCentredString(width/2, box_top - 12*mm, f"{t_years}年間で戻ってくるお金の目安：")
    p.setFillColor(colors.red)
    p.setFont(font_name, 30)
    p.drawCentredString(width/2, box_top - 25*mm, f"約 {t_total/10000:,.0f} 万円")
    p.setFillColor(colors.black)
    p.setFont(font_name, 9)
    p.drawCentredString(width/2, box_top - 32*mm, f"※借入{res_data['標準プラン']['loan']/10000:,.0f}万円、金利{res_data['標準プラン']['rate']:.1f}%、控除率{t_rate}%、上限{t_limit/10000:,.0f}万円で試算")

    graph_y = box_top - box_h - 105*mm 
    img_bytes = plot_fig.to_image(format="png", width=600, height=350)
    img_reader = ImageReader(BytesIO(img_bytes))
    p.drawImage(img_reader, 20*mm, graph_y, width=160*mm, height=100*mm, mask='auto')
    
    y_comp = graph_y - 10*mm
    p.setFont(font_name, 14)
    p.drawString(20*mm, y_comp, "【実質的な月々負担額のイメージ】")
    
    m_pay = res_data['標準プラン']['payment']
    m_tax = t_total / (t_years * 12)
    m_real = m_pay - m_tax
    
    t_data = [
        ["本来の月々返済額", f"{m_pay:,.0f} 円"],
        [f"還付金（月換算）", f"▲ {m_tax:,.0f} 円"],
        ["実質の月々負担額", f"{m_real:,.0f} 円"],
    ]
    tt = Table(t_data, colWidths=[80*mm, 60*mm], rowHeights=15*mm)
    tt.setStyle(TableStyle([
        ('FONT', (0,0), (-1,-1), font_name, 14), ('GRID', (0,0), (-1,-1), 1, colors.grey),
        ('BACKGROUND', (0,0), (0,-1), colors.lightgrey), ('ALIGN', (1,0), (1,-1), 'RIGHT'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TEXTCOLOR', (0,1), (1,1), colors.red), ('BACKGROUND', (0,2), (-1,2), colors.yellow), ('FONTSIZE', (0,2), (-1,2), 16),
    ]))
    
    tt.wrapOn(p, width, height)
    tt.drawOn(p, 30*mm, y_comp - 5*mm - 45*mm)
    
    p.setFillColor(colors.red) 
    p.setFont(font_name, 10)
    
    footer_text_1 = "※本シミュレーションは概算です。実際の還付額は、お客様の納税額（所得税・住民税）によって大きく異なります。"
    footer_text_2 = "正確な条件・金額等は税務署等にご確認ください。"
    
    p.drawCentredString(width/2, 20*mm, footer_text_1)
    p.drawCentredString(width/2, 15*mm, footer_text_2)
    
    p.showPage()
    
    # === 3ページ目以降 ===
    for price in [1000, 2000, 3000, 4000, 5000]:
        img_path = get_plan_image_path(price)
        if img_path:
            p.drawImage(img_path, 0, 0, width=width, height=height, preserveAspectRatio=True, anchor='c')
            p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

font_ready = setup_japanese_font()

if font_ready:
    pdf_merged = create_merged_pdf(
        customer_name, income_man, results, land_price_fixed,
        tax_total, tax_limit*10000, tax_rate, tax_years, fig_tax
    )
    st.download_button("📄 提案書フルセットをダウンロード", data=pdf_merged, file_name="proposal_full_set.pdf", mime="application/pdf")
    target_img = None
    b_val = results["標準プラン"]["building"] / 10000
    if b_val < 2000: target_img = get_plan_image_path(1000)
    elif b_val < 3000: target_img = get_plan_image_path(2000)
    elif b_val < 4000: target_img = get_plan_image_path(3000)
    elif b_val < 5000: target_img = get_plan_image_path(4000)
    else: target_img = get_plan_image_path(5000)
    if target_img:
        st.subheader("④ 建物プラン例")
        st.image(target_img, caption="標準プランのイメージ")
else:
    st.error("⚠️ フォントファイル (ipaexg.ttf) が見つかりません！")
