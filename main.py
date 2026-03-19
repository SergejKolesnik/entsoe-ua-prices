import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import csv

def get_exchange_rate():
    try:
        res = requests.get("https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=EUR&json")
        return res.json()[0]['rate']
    except:
        return 45.5

def fetch_prices(target_date, api_key):
    url = "https://web-api.tp.entsoe.eu/api"
    # ОЕС України
    UA_EIC = '10Y1001C--00003F'
    
    # Формуємо період на добу (24 години)
    start_str = target_date.strftime('%Y%m%d0000')
    end_str = (target_date + timedelta(days=1)).strftime('%Y%m%d0000')
    
    params = {
        'securityToken': api_key,
        'documentType': 'A44',
        'processType': 'A01',
        'in_Domain': UA_EIC,
        'out_Domain': UA_EIC,
        'periodStart': start_str,
        'periodEnd': end_str
    }
    
    print(f"Запит до ENTSO-E за дату: {target_date.date()}...")
    try:
        response = requests.get(url, params=params)
        if response.status_code != 200:
            print(f"API Error {response.status_code}: {response.text}")
            return None
        
        root = ET.fromstring(response.content)
        # Використовуємо універсальний пошук тегів без жорсткої прив'язки до namespace
        points = root.findall(".//{*}Point")
        return points
    except Exception as e:
        print(f"Помилка запиту: {e}")
        return None

if __name__ == "__main__":
    token = os.getenv('ENTSOE_TOKEN')
    now = datetime.utcnow()
    
    # Спроба 1: На завтра
    target = now + timedelta(days=1)
    points = fetch_prices(target, token)
    
    # Спроба 2: Якщо на завтра немає, беремо на сьогодні
    if not points:
        print("На завтра порожньо, пробуємо на сьогодні...")
        target = now
        points = fetch_prices(target, token)
    
    if points:
        rate = get_exchange_rate()
        file_name = 'prices_history.csv'
        file_exists = os.path.isfile(file_name)
        
        with open(file_name, mode='a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['Date', 'Hour', 'Price_EUR', 'Price_UAH', 'Rate'])
            
            for p in points:
                pos = p.find('{*}position').text
                val = p.find('{*}price.amount').text
                hour = f"{int(pos)-1:02d}:00"
                p_uah = round(float(val) * rate, 2)
                writer.writerow([target.date(), hour, val, p_uah, rate])
        
        print(f"Успішно! Додано {len(points)} записів за {target.date()}.")
    else:
        print("Критична помилка: Дані не знайдено в обох спробах.")
