import requests
try:
    r = requests.get('http://localhost:8003/exercises')
    print("Status:", r.status_code)
    print("Body:", r.text)
except Exception as e:
    print(e)
