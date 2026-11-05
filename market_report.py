#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股行业收盘日报 · 自动邮件推送
============================================================
内容: 31 个申万一级行业当日涨跌幅 + PE + 近 10 年 PE 估值分位
数据: AKShare(免费开源, 无需 API Key)
发送: QQ 邮箱 SMTP(SSL 465)
调度: cron / Windows 任务计划 / GitHub Actions

依赖: pip install akshare pandas
用法: python market_report.py            抓数据并发送邮件
     python market_report.py --dry-run  只生成 report.html, 不发信
"""

import logging
import os
import smtplib
import sys
import time
from datetime import datetime, timedelta
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

import akshare as ak
import pandas as pd

# ========================== 配置区 ==========================
MAIL_FROM = "748939530@qq.com"                     # 发件邮箱(QQ邮箱)
MAIL_NAME = "收盘小助手"
MAIL_AUTH_CODE = os.getenv("MAIL_AUTH_CODE", "")   # QQ邮箱 SMTP 授权码(推荐用环境变量)
MAIL_TO = ["748939530@qq.com"]                     # 收件人
SMTP_HOST, SMTP_PORT = "smtp.qq.com", 465

LOOKBACK_YEARS = 10            # PE 估值分位回溯窗口(年)
SEND_ON_NON_TRADING_DAY = False  # 非交易日是否照常发信
# ============================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# -------------------------- 数据抓取 --------------------------
def pick_col(df, *keywords):
    """按关键词模糊匹配列名，兼容接口字段微调"""
    for kw in keywords:
        for col in df.columns:
            if kw in str(col):
                return col
    return None


def fetch_sw_level1(start_date, end_date):
    """分自然年拉取申万一级行业日度分析报表(涨跌幅+市盈率)"""
    frames = []
    for year in range(start_date.year, end_date.year + 1):
        seg_s = max(start_date, datetime(year, 1, 1))
        seg_e = min(end_date, datetime(year, 12, 31))
        if seg_s > seg_e:
            continue
        try:
            df = ak.index_analysis_daily_sw(
                symbol="一级行业",
                start_date=seg_s.strftime("%Y%m%d"),
                end_date=seg_e.strftime("%Y%m%d"),
            )
        except Exception as exc:
            logging.warning("拉取 %s 年数据失败: %s", year, exc)
            continue
        if df is not None and not df.empty:
            frames.append(df)
        time.sleep(0.6)  # 控频，避免被数据源限流
    if not frames:
        raise RuntimeError("未获取到申万一级行业数据，请检查网络或 akshare 版本")
    return pd.concat(frames, ignore_index=True)


def build_report(raw):
    col_date = pick_col(raw, "日期", "交易日期")
    col_name = pick_col(raw, "行业名称", "指数名称")
    col_code = pick_col(raw, "行业代码", "指数代码")
    col_chg = pick_col(raw, "涨跌幅")
    col_pe = pick_col(raw, "市盈率")

    missing = [n for n, c in [("日期", col_date), ("行业名称", col_name),
                              ("涨跌幅", col_chg), ("市盈率", col_pe)] if c is None]
    if missing:
        raise RuntimeError(f"数据缺少字段 {missing}，实际列名: {list(raw.columns)}")

    cols = {col_date: "date", col_name: "name", col_chg: "chg", col_pe: "pe"}
    if col_code:
        cols[col_code] = "code"
    df = raw[list(cols)].rename(columns=cols)

    s = df["date"].astype(str).str.replace(r"\D", "", regex=True)
    df["date"] = pd.to_datetime(s, format="%Y%m%d", errors="coerce")
    for c in ("chg", "pe"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["date", "name"])

    # 按行业代码分组(行业改名不影响历史序列)，展示名取最新一行
    key = df["code"] if "code" in df.columns else df["name"]
    rows = []
    for _, grp in df.groupby(key, sort=False):
        grp = grp.sort_values("date")
        cur = grp.iloc[-1]
        pe_hist = grp["pe"].dropna()
        pe_hist = pe_hist[pe_hist > 0]
        cur_pe = cur["pe"]
        pct = None
        if pd.notna(cur_pe) and cur_pe > 0 and not pe_hist.empty:
            pct = float((pe_hist <= cur_pe).sum()) / len(pe_hist) * 100.0
        rows.append({"name": cur["name"], "chg": cur["chg"], "pe": cur_pe, "pct": pct})

    rep = pd.DataFrame(rows)
    rep = rep.sort_values("chg", ascending=False, na_position="last").reset_index(drop=True)
    return rep, df["date"].max()


# -------------------------- 邮件渲染 --------------------------
def val_tag(pct):
    if pct is None:
        return "—", "#8a857c"
    if pct < 30:
        return "低估", "#1f5fa8"
    if pct <= 70:
        return "适中", "#6b6559"
    return "偏贵", "#b3402a"


def render_html(rep, data_date):
    up = int((rep["chg"] > 0).sum())
    down = int((rep["chg"] < 0).sum())
    flat = len(rep) - up - down
    avg = rep["chg"].mean()
    avg_txt = f"{avg:+.2f}%" if pd.notna(avg) else "—"
    low_cnt = int((rep["pct"].dropna() < 30).sum())

    trs = []
    for i, r in rep.iterrows():
        chg = r["chg"]
        if pd.isna(chg):
            chg_txt, chg_color = "—", "#8a857c"
        else:
            chg_txt = f"{chg:+.2f}%"
            chg_color = "#c0392b" if chg > 0 else ("#1e8449" if chg < 0 else "#6b6559")
        pe_txt = "—" if pd.isna(r["pe"]) or r["pe"] <= 0 else f"{r['pe']:.1f}"
        pct_txt = "—" if r["pct"] is None else f"{r['pct']:.0f}%"
        tag, tag_color = val_tag(r["pct"])
        bg = "#faf8f4" if i % 2 else "#ffffff"
        trs.append(
            f'<tr style="background:{bg};">'
            f'<td style="padding:9px 14px;border-bottom:1px solid #eee7dc;font-size:14px;color:#2c2a26;">{r["name"]}</td>'
            f'<td style="padding:9px 14px;border-bottom:1px solid #eee7dc;font-size:14px;font-weight:600;color:{chg_color};text-align:right;">{chg_txt}</td>'
            f'<td style="padding:9px 14px;border-bottom:1px solid #eee7dc;font-size:14px;color:#2c2a26;text-align:right;">{pe_txt}</td>'
            f'<td style="padding:9px 14px;border-bottom:1px solid #eee7dc;font-size:14px;color:#2c2a26;text-align:right;">{pct_txt}</td>'
            f'<td style="padding:9px 14px;border-bottom:1px solid #eee7dc;font-size:13px;color:{tag_color};text-align:center;">{tag}</td>'
            f"</tr>"
        )
    rows_html = "".join(trs)

    top3 = "，".join(f"{r['name']} {r['chg']:+.2f}%" for _, r in rep.head(3).iterrows() if pd.notna(r["chg"]))
    bot3 = "，".join(f"{r['name']} {r['chg']:+.2f}%" for _, r in rep.tail(3).iterrows() if pd.notna(r["chg"]))

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f1ede6;">
<div style="width:100%;background:#f1ede6;padding:26px 10px;">
  <div style="max-width:660px;margin:0 auto;background:#ffffff;border:1px solid #e2dbcd;">

    <div style="background:#20201d;padding:22px 26px;">
      <div style="font-size:11px;letter-spacing:4px;color:#d8b24c;">MARKET CLOSE REPORT</div>
      <div style="font-size:23px;font-weight:700;color:#f7f3ea;margin-top:8px;">A股行业收盘日报</div>
      <div style="font-size:12px;color:#a29a8c;margin-top:8px;">{data_date:%Y-%m-%d} · 31个申万一级行业 · 涨跌幅 / PE / 近{LOOKBACK_YEARS}年估值分位</div>
    </div>

    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
      <tr>
        <td width="25%" style="padding:16px 8px;text-align:center;border-bottom:3px solid #c0392b;">
          <div style="font-size:11px;color:#8a857c;">上涨</div>
          <div style="font-size:20px;font-weight:700;color:#c0392b;margin-top:4px;">{up}</div>
        </td>
        <td width="25%" style="padding:16px 8px;text-align:center;border-bottom:3px solid #1e8449;">
          <div style="font-size:11px;color:#8a857c;">下跌</div>
          <div style="font-size:20px;font-weight:700;color:#1e8449;margin-top:4px;">{down}</div>
        </td>
        <td width="25%" style="padding:16px 8px;text-align:center;border-bottom:3px solid #c9c1b2;">
          <div style="font-size:11px;color:#8a857c;">平盘</div>
          <div style="font-size:20px;font-weight:700;color:#6b6559;margin-top:4px;">{flat}</div>
        </td>
        <td width="25%" style="padding:16px 8px;text-align:center;border-bottom:3px solid #d8b24c;">
          <div style="font-size:11px;color:#8a857c;">平均涨跌幅</div>
          <div style="font-size:20px;font-weight:700;color:#2c2a26;margin-top:4px;">{avg_txt}</div>
        </td>
      </tr>
    </table>

    <div style="padding:14px 26px;font-size:12.5px;color:#4a463f;line-height:1.9;">
      <div><b style="color:#c0392b;">涨幅前三：</b>{top3}</div>
      <div><b style="color:#1e8449;">跌幅前三：</b>{bot3}</div>
      <div><b style="color:#1f5fa8;">低估区（PE分位&lt;30%）行业：</b>{low_cnt} 个</div>
    </div>

    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
      <tr style="background:#2c2a26;">
        <td style="padding:11px 14px;font-size:12px;color:#e8e2d5;letter-spacing:1px;">行业</td>
        <td style="padding:11px 14px;font-size:12px;color:#e8e2d5;letter-spacing:1px;text-align:right;">涨跌幅</td>
        <td style="padding:11px 14px;font-size:12px;color:#e8e2d5;letter-spacing:1px;text-align:right;">PE</td>
        <td style="padding:11px 14px;font-size:12px;color:#e8e2d5;letter-spacing:1px;text-align:right;">PE分位</td>
        <td style="padding:11px 14px;font-size:12px;color:#e8e2d5;letter-spacing:1px;text-align:center;">估值状态</td>
      </tr>
      {rows_html}
    </table>

    <div style="padding:18px 26px;font-size:11px;color:#8a857c;line-height:1.8;border-top:1px solid #eee7dc;">
      数据源：AKShare · 申万一级行业指数分析报表（市盈率为申万报表口径）。
      PE分位 = 当前 PE 在近 {LOOKBACK_YEARS} 年日频 PE 样本中的百分位（脚本自行计算）；PE≤0 或无历史数据的行业显示"—"。
      本邮件由自动化脚本生成，仅供参考，不构成投资建议。
    </div>

  </div>
</div>
</body></html>"""


def render_error_html(err):
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;background:#f1ede6;padding:30px;font-family:sans-serif;">
<div style="max-width:600px;margin:auto;background:#fff;border:1px solid #e2dbcd;padding:24px;">
  <div style="font-size:18px;font-weight:700;color:#b3402a;">收盘日报生成失败</div>
  <div style="margin-top:12px;font-size:13px;color:#444;">错误信息：</div>
  <pre style="background:#faf7f1;padding:12px;font-size:12px;white-space:pre-wrap;">{err}</pre>
  <div style="margin-top:12px;font-size:12px;color:#8a857c;">请检查网络、akshare 版本（pip install -U akshare）或接口是否变更。</div>
</div></body></html>"""


# -------------------------- 邮件发送 --------------------------
def send_mail(html, subject):
    if not MAIL_AUTH_CODE:
        raise SystemExit("缺少 MAIL_AUTH_CODE：请在 QQ邮箱网页版 → 设置 → 账户 → 开启 SMTP 服务并生成授权码")
    msg = MIMEText(html, "html", "utf-8")
    msg["From"] = formataddr((str(Header(MAIL_NAME, "utf-8")), MAIL_FROM))
    msg["To"] = ", ".join(MAIL_TO)
    msg["Subject"] = Header(subject, "utf-8")
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.login(MAIL_FROM, MAIL_AUTH_CODE)
        server.sendmail(MAIL_FROM, MAIL_TO, msg.as_string())


def main():
    dry_run = "--dry-run" in sys.argv
    now = datetime.now()
    start = now - timedelta(days=int(LOOKBACK_YEARS * 365.25))
    logging.info("抓取申万一级行业数据: %s ~ %s", start.date(), now.date())

    try:
        raw = fetch_sw_level1(start, now)
        rep, data_date = build_report(raw)
    except Exception as exc:
        logging.exception("报告生成失败")
        if not dry_run:
            send_mail(render_error_html(str(exc)), f"收盘日报生成失败 | {now:%Y-%m-%d}")
        raise SystemExit(1)

    if data_date.date() != now.date() and not SEND_ON_NON_TRADING_DAY:
        logging.info("最新数据日为 %s，非交易日或数据未更新，不发送", data_date.date())
        return

    subject = f"A股收盘日报 | {data_date:%Y-%m-%d} | 31行业涨跌与PE分位"
    html = render_html(rep, data_date)
    if dry_run:
        with open("report.html", "w", encoding="utf-8") as f:
            f.write(html)
        logging.info("dry-run 完成，已写入 report.html")
        return
    send_mail(html, subject)
    logging.info("已发送: %s", subject)


if __name__ == "__main__":
    main()