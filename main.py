import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import csv

def get_ua_prices():
    api_key = os.getenv('ENTSOE_TOKEN')
    url = "https://web-api.tp.entsoe.eu/api"
    UA_EIC = '10Y1001C--00003F'
    
    # Шукаємо дані на завтра (РДН)
    target_date = datetime.utcnow() + timedelta(days=1)
    start = target_date.strftime('%Y%m%d0000')
    end = (target_date + timedelta(days=1)).strftime('%Y%m%d0000')
    
    params = {
        'securityToken': api_key,
        'documentType': 'A44',
        'processType': 'A01',
        'in_Domain': UA_EIC,
        'out_Domain': UA_EIC,
        'periodStart': start,
        'periodEnd': end
    }
    
    print(f"Запит до ENTSO-E за дату: {target_date.date()}...")
    try:
        r = requests.get(url, params=params)
        # Якщо завтрашніх ще немає, спробуємо за сьогодні
        if r.status_code != 200 or '<Point>' not in r.text:
            print("На завтра порожньо, перевіряємо сьогодні...")
            target_date = datetime.utcnow()
            params['periodStart'] = target_date.strftime('%Y%m%d0000')
            params['periodEnd'] = (target_date + timedelta(days=1)).strftime('%Y%m%d0000')
            r = requests.get(url, params=params)

        if r.status_code == 200 and '<Point>' in r.text:
            root = ET.fromstring(r.content)
            # Знаходимо валюту (UAH або EUR)
            currency = root.find(".//{*}currency_Unit.name")
            curr_text = currency.text if currency is not None else "N/A"
            
            points = root.findall(".//{*}Point")
            file_name = 'prices_history.csv'
            file_exists = os.path.isfile(file_name)
            
            with open(file_name, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(['Date', 'Hour', 'Price', 'Currency'])
                
                for p in points:
                    pos = p.find('{*}position').text
                    val = p.find('{*}price.amount').text
                    # Ми використовуємо універсальний пошук тегів
                    hour = f"{int(pos)-1:02d}:00"
                    writer.writerow([target_date.date(), hour, val, curr_text])
            
            print(f"Успішно! Додано {len(points)} записів за {target_date.date()} ({curr_text})")
        else:
            print(f"Помилка: Дані за {target_date.date()} на платформі недоступні.")
            # Додаткова діагностика
            if r.status_code != 200:
                print(f"Відповідь сервера: {r.status_code} {r.text}")

    except Exception as e:
        print(f"Помилка запиту: {e}")

if __name__ == "__main__":
    get_ua_prices()
