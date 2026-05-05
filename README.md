# 就业岗位查询

输入城市和专业方向，聚合多平台招聘信息。

## 数据源

- BOSS直聘
- 51job
- 智联招聘
- 微信公众号（搜狗微信搜索）
- 搜索引擎（DuckDuckGo）

## 运行

```bash
pip install -r requirements.txt
python app.py
```

浏览器打开 `http://127.0.0.1:5000`

## 技术栈

Python + Flask + httpx + BeautifulSoup，前端 Vanilla JS 单页。
