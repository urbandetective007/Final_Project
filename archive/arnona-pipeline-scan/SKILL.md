---
name: arnona-pipeline-scan
description: >
  סריקת כתובות ארנונה ירושלמיות לאיתור עסקים פעילים — ADDRESS-FIRST pipeline.
  השתמש בסקיל הזה בכל פעם שהמשתמש מבקש להריץ את צינור הארנונה, לסרוק כתובות מקובץ ארנונה,
  לאתר עסקים בכתובות מגורים, להמשיך סריקה מאינדקס קודם, לעדכן את GitHub עם הממצאים,
  או לטעון נתונים ל-Supabase ממקובץ ארנונה. הסקיל מריץ 6+ חיפושי Tavily לכל כתובת,
  בונה קובץ Excel בפורמט arnona-upload, מעלה ל-Supabase, ומעדכן את אינדקס ההמשך ב-GitHub.
  הפעל גם כשהמשתמש אומר "המשך סריקה", "הרץ את הפייפליין", "בדוק כתובות ארנונה".
compatibility:
  tools:
    - tavily_search (Tavily MCP)
    - tavily_extract (Tavily MCP)
    - bash_tool
  python_packages:
    - pandas
    - openpyxl
    - requests
  external:
    - GitHub repo: https://github.com/urbandetective007/Arnona_Agent.git
    - Supabase (credentials in arnona-upload.md)
---

# Arnona Pipeline Scan — ADDRESS-FIRST

סריקה סדרתית של כתובות ארנונה, איתור עסקים פעילים, העלאה ל-Supabase ועדכון אינדקס ב-GitHub.

---

## עקרונות יסוד

- **סדרתי בלבד**: מעבדים כתובת אחת בכל פעם. לא מתחילים כתובת N+1 לפני שכתובת N הסתיימה עם ✅.
- **Tavily MCP בלבד**: משתמשים ב-`tavily_search` ו-`tavily_extract` מה-MCP connector. אין שימוש ב-Python Tavily client.
- **מינימום 6 חיפושים לכתובת**: לכל כתובת מריצים לפחות 6 שאילתות חיפוש.
- **כתובת מקורית תמיד**: בעמודת `כתובת` — תמיד הכתובת שנלקחה מקובץ הארנונה, לא כתובת מהאינטרנט.

---

## STEP 0 — Setup

```bash
git clone https://github.com/urbandetective007/Arnona_Agent.git /tmp/repo
pip install pandas openpyxl requests -q
python -c "import zipfile; zipfile.ZipFile('/tmp/repo/skills/business-address-lookup.skill').extractall('/tmp/skill_lookup')"
cat /tmp/skill_lookup/business-address-lookup/SKILL.md
cat /tmp/repo/skills/arnona-upload.md
```

קרא את שני הקבצים לפני שממשיכים.

---

## STEP 1 — טעינת אינדקס המשך מ-GitHub

```bash
N_RAW=$(cat /tmp/repo/reports/arnona_next_index.txt 2>/dev/null | tr -d '[:space:]')
if [[ "$N_RAW" =~ ^[0-9]+$ ]]; then
  N=$N_RAW
else
  N=0
  echo "⚠️ Index file missing or invalid — starting from 0"
fi
echo "Starting from index: $N"
```

---

## STEP 1b — אתחול מונה tokens

```python
MAX_TOKENS = 150_000
TOKEN_LIMIT_PCT = 0.70
tokens_used = 0
token_limit_reached = False

def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)

def check_token_budget(label: str = "") -> bool:
    if tokens_used >= MAX_TOKENS * TOKEN_LIMIT_PCT:
        print(f"⛔ Token usage {tokens_used}/{MAX_TOKENS} ({100*tokens_used/MAX_TOKENS:.1f}%) ≥ 70% {label} — stopping.")
        return True
    return False

print(f"Token budget initialized: max {MAX_TOKENS:,}, stop at {int(MAX_TOKENS * TOKEN_LIMIT_PCT):,}")
```

עצירה אוטומטית ב-70% מהתקציב — מבטיחה שיישאר מרווח לבנייה והעלאה.

---

## STEP 2 — טעינת כתובות מהאקסל

```python
import pandas as pd

df = pd.read_excel('/tmp/repo/scripts/data/arnona_data.xlsx')
addresses = list(dict.fromkeys(
    str(v).strip() for v in df.iloc[:, 0] if pd.notna(v)
))

if N >= len(addresses):
    N = 0
    print("⚠️ Index exceeded address list length — wrapping to 0")

print(f"Loaded {len(addresses)} addresses. Starting at index {N}.")
```

---

## STEP 3 — לולאת סריקה (סדרתית)

```
businesses_found = []
last_index = N - 1
MAX_RETRIES = 2

For each address starting at index N:
```

### לפני כל כתובת:
```python
if check_token_budget(f"before address {current_index}"):
    token_limit_reached = True
    break
```

### ביצוע הסריקה:

1. קרא את `business-address-lookup` SKILL.md (כבר נטען ב-STEP 0).
2. הרץ **לפחות 6 שאילתות Tavily** לכתובת הנוכחית, למשל:
   - `"{address}" רופא שיניים`
   - `"{address}" עורך דין`
   - `"{address}" קליניקה`
   - `"{address}" רואה חשבון`
   - `"{address}" עסק`
   - `site:d.co.il "{address}"`
3. לכל URL מבטיח — הרץ `tavily_extract` לאימות.

### ספירת tokens:
```python
tokens_used += estimate_tokens(address)
for query in queries_sent:
    tokens_used += estimate_tokens(query)
for result in results_received:
    tokens_used += estimate_tokens(str(result))
```

### אם אפס עסקים נמצאו:
- נסה שוב עד `MAX_RETRIES` פעמים עם שאילתות מנוסחות אחרת.
- ספור tokens לכל ניסיון חוזר.
- אם עדיין אפס — רשום ועבור לכתובת הבאה.

### הוספה לרשימה (עסק מאומת בלבד):
```python
businesses_found.append({
    "שם העסק": business_name,
    "כתובת": address,          # ← תמיד מקובץ הארנונה!
    "סוג העסק": category,
    "source_url": url,
})
```

### אחרי כל כתובת:
```python
last_index = current_index

if check_token_budget(f"after address {current_index}"):
    token_limit_reached = True
    break
```

---

## STEP 4 — בניית /tmp/report.xlsx

### עמודות (Hebrew, exact order):

| עמודה | ערך |
|-------|-----|
| `שם העסק` | שם העסק |
| `סוג העסק` | קטגוריה |
| `כתובת` | כתובת מקובץ הארנונה |
| `דירוג אינדיקציה` | `גבוה` |
| `כתובת תואמת (מהעירייה)` | זהה לעמודת `כתובת` |
| `שמות בעלי נכסים` | `—` |
| `מס' דירות` | `—` |
| `פירוט האינדיקציה` | `נמצא בחיפוש אינטרנט בכתובת מגורים ממרשימת הארנונה` |
| `סיבת אי-אינדיקציה` | (ריק) |
| `מקור המידע (URL)` | source URL |

```python
import pandas as pd

if not businesses_found:
    print("No businesses found — skipping Excel build and upload.")
    # → go to STEP 6
else:
    rows = []
    for b in businesses_found:
        rows.append({
            "שם העסק": b["שם העסק"],
            "סוג העסק": b["סוג העסק"],
            "כתובת": b["כתובת"],
            "דירוג אינדיקציה": "גבוה",
            "כתובת תואמת (מהעירייה)": b["כתובת"],
            "שמות בעלי נכסים": "—",
            "מס' דירות": "—",
            "פירוט האינדיקציה": "נמצא בחיפוש אינטרנט בכתובת מגורים ממרשימת הארנונה",
            "סיבת אי-אינדיקציה": "",
            "מקור המידע (URL)": b["source_url"],
        })

    df_out = pd.DataFrame(rows)
    df_out.to_excel("/tmp/report.xlsx", index=False)
    print(f"✅ /tmp/report.xlsx created with {len(rows)} rows.")
```

---

## STEP 5 — העלאה ל-Supabase

הרץ את הסקריפט שמוגדר ב-`/tmp/repo/skills/arnona-upload.md` על `/tmp/report.xlsx`.

- **הצלחה** → עדכן `reports/arnona_next_index.txt` ל-`last_index + 1` ודחוף ל-main:
  ```bash
  echo $((last_index + 1)) > /tmp/repo/reports/arnona_next_index.txt
  cd /tmp/repo && git add reports/arnona_next_index.txt && git commit -m "update index to $((last_index + 1))" && git push origin main
  ```
- **כישלון** → רשום שגיאה, **אל תעדכן את האינדקס** (כדי שהכתובות יחזרו בריצה הבאה).

---

## STEP 6 — סיכום סופי (עברית)

הצג סיכום הכולל:

- **כמה כתובות עובדו** — מאינדקס `N` עד `last_index`
- **כמה עסקים נמצאו** — שמות וכתובות
- **האם הופסק בגלל מגבלת tokens** (70%)
- **סה"כ tokens** — `{tokens_used:,} / {MAX_TOKENS:,} ({100*tokens_used/MAX_TOKENS:.1f}%)`
- **האם ההעלאה ל-Supabase הצליחה**
- **האם האינדקס עודכן ב-GitHub** (הערך החדש)

---

## טיפים לאיתור שגיאות

| בעיה | פתרון |
|------|-------|
| `arnona_next_index.txt` חסר | מתחיל מ-0 אוטומטית |
| אינדקס גדול מרשימת הכתובות | wrap ל-0 |
| Tavily MCP לא זמין | בדוק שה-connector מחובר ב-Claude.ai |
| העלאה ל-Supabase נכשלה | לא מעדכן אינדקס — אותן כתובות יחזרו בריצה הבאה |
| כתובת בלי עסקים אחרי retries | ממשיך לכתובת הבאה, לא מדלג על האינדקס |
