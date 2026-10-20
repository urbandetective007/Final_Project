# Tavily עם כמה מפתחות

`tavily.py` מחליף את ה-Connector של Tavily ברוטינה: הוא קורא ל-API ישירות עם רשימת מפתחות,
ועובר אוטומטית למפתח הבא כשהמכסה של מפתח נגמרת (432/433) או שהמפתח לא תקין (401).

## הגדרה (פעם אחת)
במשתנה הסביבה `TAVILY_API_KEYS` של סביבת הענן — כל המפתחות מופרדים בפסיק:

```
TAVILY_API_KEYS=tvly-xxxx,tvly-yyyy
```

(בהגדרות הסביבה: תפריט הסביבה בכותרת הסשן → Edit → משתני סביבה.) מפתח חדש = להוסיף אותו לרשימה. אין צורך לשנות את הרוטינה.

## שימוש
```bash
python3 tools/tavily/tavily.py status                       # קרדיט שנשאר בכל מפתח; יציאה 3 = כולם גמורים, 2 = אין מפתחות
python3 tools/tavily/tavily.py search '"יפו 1" ירושלים עסקים' --max-results 10
python3 tools/tavily/tavily.py search '"יפו 1"' --include-domains b144.co.il
python3 tools/tavily/tavily.py extract https://www.b144.co.il/... --query "כתובת טלפון שעות תחום"
```

| כלי ה-Connector | הפקודה |
|---|---|
| `tavily_search(query=...)` | `tavily.py search "<query>"` |
| `tavily_extract(urls=[...], query=...)` | `tavily.py extract <url> ... --query "<query>"` |

הפלט JSON. מפתחות לא מודפסים לעולם — רק 4 התווים האחרונים (`…abcd`).
