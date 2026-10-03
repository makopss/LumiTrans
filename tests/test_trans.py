import os as _os
import sys as _sys

# 프로젝트 루트를 import 경로에 추가 (tests/ 폴더에서 실행되므로)
_PROJECT_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)

import requests
import re
import html

text = 'Welcome back everyone to our channel.'

# 1. Google mobile
url = 'https://translate.google.com/m'
params = {'sl': 'en', 'tl': 'ko', 'q': text}
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
try:
    r = requests.get(url, params=params, headers=headers, timeout=5)
    print('Google /m status:', r.status_code)
    if r.status_code == 200:
        match = re.search(r'class="result-container">(.*?)</div>', r.text)
        if match:
            print('Google /m result:', html.unescape(match.group(1)))
        else:
            print('Google /m no match, length:', len(r.text))
except Exception as e:
    print('Google /m err:', e)

# 2. MyMemory direct
try:
    url2 = f'https://api.mymemory.translated.net/get?q={text}&langpair=en|ko'
    r2 = requests.get(url2, timeout=5)
    print('MyMemory status:', r2.status_code)
    if r2.status_code == 200:
        res = r2.json()
        print('MyMemory direct:', res['responseData']['translatedText'])
except Exception as e:
    print('MyMemory direct err:', e)
