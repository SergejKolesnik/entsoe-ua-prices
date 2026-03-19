import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import csv

def fetch_entsoe(target_date, api_key, process_type='A01'):
    url = "https://web-api.tp.entsoe.eu/api"
    UA_EIC = '10Y1001C--00003F'
    
    # Використовуємо ширше вікно часу, щоб уникнути проблем з поясами
    start = target_date.replace(hour=0, minute=0).strftime('%Y%m%d%H%M')
    end = (target_date + timedelta(days=1)).replace(hour=0, minute=0).strftime('%Y%m%d%H%M')
    
    params = {
        'securityToken': api_key,
        'documentType': 'A44',
        'processType': process_type, # A01 - Day Ahead, A16 - Realised
        'in_Domain': UA_EIC,
        'out_Domain': UA_EIC,
        'periodStart': start,
        'periodEnd': end
    }
    
    try:
        r = requests.get(url, params=params)
        if r.status_code == 200 and '<Point>' in r.text:
            return ET.fromstring(r.content), target_date.date()
    except:
        pass
    return None, None

if __name__ == "__main__":
    token = os.getenv('ENTSOE_TOKEN')
    now = datetime.utcnow()
    
    # Список дат для перевірки: завтра, потім сьогодні
    dates_to_check = [now + timedelta(days=1), now]
    # Список типів процесів: стандартний та альтернативний (для "Without Sequence")
    processes = ['A01', 'A16']
    
    found_data = False
    for date_dt in dates_to_check:
        for proc in processes:
            print(f"Пробуємо отримати дані за {date_dt.date()} (Тип: {proc})...")
            root, final_date = fetch_entsoe(date_dt, token, proc)
            
            if root:
                points = root.findall(".//{*}Point")
                if points:
                    currency = root.find(".//{*}currency_Unit.name")
                    curr_text = currency.text if currency is not None else "UAH"
                    
                    file_name = 'prices_history.csv'
                    file_exists = os.path.isfile(file_name)
                    
                    with open(file_name, 'a', newline='') as f:
                        writer = csv.writer(f)
                        if not file_exists:
                            writer.writerow(['Date', 'Hour', 'Price', 'Currency'])
                        
                        for p in points:
                            pos = p.find('{*}position').text
                            val = p.find('{*}price.amount').text
                            writer.writerow([final_date, f"{int(pos)-1:02d}:00", val, curr_text])
                    
                    print(f"Успішно! Знайдено дані за {final_date} ({curr_text}).")
                    found_data = True
                    break
        if found_data: break

    if not found_data:
        print("Критична помилка: Дані на платформі є, але API їх не віддає за стандартними кодами.")
