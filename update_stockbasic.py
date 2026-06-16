import time
import pandas as pd
import requests
import json
from pytdx.hq import TdxHq_API
from src.common.mysql_utils import db, StockBasic  # 确保你已经定义了模型并绑定了 db

# --- 配置 ---
HOST = '117.133.128.226'
PORT = 7709

def get_bse_codes_from_official():
    """从北交所官网抓取名单"""
    url = f"https://www.bse.cn/nqhqController/nqhq_en.do?callback=jQuery_{int(time.time()*1000)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/123.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
    }
    stock_list = []
    for page in range(20):
        payload = f"page={page}&type_en=%5B%22B%22%5D&sortfield=hqcjsl&sorttype=desc&xxfcbj_en=%5B2%5D&zqdm="
        try:
            resp = requests.post(url, data=payload, headers=headers)
            json_str = resp.text[resp.text.find("(")+1 : resp.text.rfind(")")]
            data = json.loads(json_str)
            elements = data[0]['content']
            if not elements: break
            for item in elements:
                stock_list.append({
                    "symbol": item['hqzqdm'],
                    "name": item['hqzqjc'],
                    "market_code": "CN",
                })
            if data[0]['lastPage']: break
            time.sleep(0.1)
        except: break
    return stock_list

def sync_all_stocks():
    start_time = time.time()
    all_data = []

    # 1. 获取沪深数据 (PyTDX)
    api = TdxHq_API()
    if api.connect(HOST, PORT):
        print("已连接通达信服务器，正在拉取沪深列表...")
        for m_id in [0, 1]: # 0:SZ, 1:SH
            m_str = "SZ" if m_id == 0 else "SH"
            count = api.get_security_count(m_id)
            for i in range(0, count, 1000):
                stocks = api.get_security_list(m_id, i)
                if stocks:
                    for s in stocks:
                        # 简单的 A 股过滤逻辑
                        code = s['code']
                        #if code.startswith(('60', '68', '00', '30','920')):
                        all_data.append({
                            "symbol": code,
                            "name": s['name'],
                            "market_code": "CN",
                        })
        api.disconnect()
    else:
        print("通达信服务器连接失败")

    # 2. 获取北京数据 (官网爬虫)
    print("正在从官网拉取北交所列表...")
    bse_stocks = get_bse_codes_from_official()
    all_data.extend(bse_stocks)

    # 3. 批量入库 (Upsert 模式)
    print(f"整理完成，共 {len(all_data)} 条有效股票记录。准备写入数据库...")
    
    # Peewee 批量操作
    with db.atomic():
        # 分批写入，防止 SQL 语句过长 (每批 500 条)
        for i in range(0, len(all_data), 500):
            batch = all_data[i:i+500]
            StockBasic.insert_many(batch).on_conflict(
                preserve=[StockBasic.name, StockBasic.market_code, StockBasic.enabled],
                update={}
            ).execute()

    end_time = time.time()
    print("---")
    print(f"同步完成！总计耗时: {end_time - start_time:.2f} 秒")
    print(f"数据已同步至表: {StockBasic._meta.table_name}")



def get_common_indexes():
    """获取常用指数列表"""
    common_indexes = [
        {"symbol": "000001", "name": "上证指数"},
        {"symbol": "000300", "name": "沪深300"},
        {"symbol": "000905", "name": "中证500"},
        {"symbol": "000852", "name": "中证1000"},
        {"symbol": "000906", "name": "中证800"},
        {"symbol": "399001", "name": "深证成指"},
        {"symbol": "399006", "name": "创业板指"},
        {"symbol": "399005", "name": "中小板指"},
    ]
    return common_indexes


if __name__ == "__main__":
    # 确保表存在
    #db.connect()
    #db.create_tables([StockBasic], safe=True)
    sync_all_stocks()