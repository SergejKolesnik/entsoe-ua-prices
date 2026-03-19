import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import csv

def fetch_data(api_key, target_date):
    url = "https://web-api.tp.entsoe.eu/api"
    # ОЕС України
    UA_EIC = '10Y1001C--00003F'
    
    # Спробуємо максимально широкий запит
    params = {
        'securityToken': api_key,
        'documentType': 'A44',
        'in_Domain': UA_EIC,
        'out_Domain': UA_EIC,
        'periodStart': target_date.strftime('%Y%m%d0000'),
        'periodEnd': (target_date + timedelta(days=1)).strftime('%Y%m%d0000')
    }
    
    print(f"--- Запит за {target_date.date()} ---")
    r = requests.get(url, params=params)
    
    if r.status_code != 200:
        print(f"Помилка сервера: {r.status_code}")
        return None

    # Якщо даних нібито немає, виведемо частину відповіді для аналізу
    if '<Point>' not in r.text:
        print("Сервер повернув відповідь, але точок (цін) у ній немає.")
        # Виводимо початок XML, щоб зрозуміти причину (наприклад, No matching data found)
        print(f"Фрагмент відповіді: {r.text[:300]}")
        return None
    
    return ET.fromstring(r.content)

if __name__ == "__main__":
    token = os.getenv('ENTSOE_TOKEN')
    now = datetime.utcnow()
    
    # Перевіряємо завтра, потім сьогодні
    for day in [now + timedelta(days=1), now]:
        root = fetch_data(token, day)
        if root:
            points = root.findall(".//{*}Point")
            currency = root.find(".//{*}currency_Unit.name")
            curr_name = currency.text if currency is not None else "UAH"
            
            file_name = 'prices_history.csv'
            file_exists = os.path.isfile(file_name)
            
            with open(file_name, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(['Date', 'Hour', 'Price', 'Currency'])
                
                for p in points:
                    pos = p.find('{*}position').text
                    val = p.find('{*}price.amount').text
                    writer.writerow([day.date(), f"{int(pos)-1:02d}:00", val, curr_name])
            
            print(f"УСПІХ! Дані за {day.date()} збережено.")
            break
    else:
        print("На жаль, API ENTSO-E для України зараз не віддає ціни через автоматичний запит.")
        print("Це може бути пов'язано з технічним статусом 'WITHOUT SEQUENCE' на сайті.")
