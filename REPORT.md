# ChefScout: סוכן אחד, שני harnesses

**מגישה:** יוכבד אלפא · **מודל:** `claude-opus-5-5`, effort `medium` בשתי הגרסאות

## 1. הסוכן

**ChefScout** הוא עוזר בישול אישי. הוא מוצא מתכונים לפי התזונה והאלרגיות שלי, מחפש מתכונים ברשת ומנהל רשימת קניות. הוא זוכר אותי בין סשנים: אם אמרתי פעם שאני אלרגית לבוטנים, הוא לא יציע לי שוב רוטב סאטה.

### ארבעת הנושאים

| נושא | איך זה ממומש |
|---|---|
| **Tools** (7, אחד חיצוני) | `search_recipes`, `get_recipe`, `add_to_shopping_list`, `get_shopping_list`, `save_memory`, `recall_memory`, ו-**`search_web_recipes`** שקורא ל-API החיצוני של TheMealDB באינטרנט. רשימת הקניות נשמרת לקובץ. הקוד נמצא ב-`shared/recipes.py`. |
| **Memory** | `shared/memory_store.py` שומר עובדות (diet, allergies, dislikes, favorites, notes...) ב-`memory.json`. ערך יחיד, כמו diet, מוחלף, והערך הישן נשמר ב-`history`. כך כשאני משנה החלטה רואים מה השתנה ומתי. |
| **Context engineering** | הקטלוג, רשימת הקניות והזיכרון המלא **לא** נשלחים בכל תור. ב-API, `memory.py` שולח תמיד רק את עובדות הבטיחות (diet, allergies, dislikes), ושאר המפתחות נכנסים רק כשההודעה עוסקת בהם (למשל favorites כשכתוב "again" או "favorite"). את השאר המודל שולף בכלים. |
| **Token optimization** | פלט הכלים קומפקטי: שורות `id\|name\|time\|diet\|allergens`, לכל היותר 5 תוצאות, הוראות מקוצרות ל-600 תווים, ותקרה של 1500 תווים לכל `tool_result`. ה-system prompt מגביל תשובה ל-120 מילים. כל תור נמדד: input, cache read, cache write, output, קריאות, עלות וזמן. |

## 2. מה בנוי בכל גרסה

| אחריות | API (`API/harness/`), כתבתי בעצמי | SDK (`SDK/`), רק הגדרתי |
|---|---|---|
| לולאה | `loop.py`: `while stop_reason == "tool_use"`. כל ה-`tool_result` חוזרים בהודעת user אחת. | `ClaudeSDKClient.query()` + `receive_response()` |
| כלים | `tools.py`: סכמות JSON, dispatch, שגיאות חוזרות כ-`is_error: true` | `@tool` + `create_sdk_mcp_server`, `tools=[]` (בלי כלים מובנים), `allowed_tools` מצומצם, `strict_mcp_config=True` |
| שיחה | `history.py`: JSONL, append-only, עם סמן compaction | `resume=session_id`, שנשמר ב-`state/sdk/sessions/` |
| זיכרון | `memory.py`: שולף רק את המפתחות הרלוונטיים | `CLAUDE.md` שנוצר מחדש אחרי כל `save_memory`, עם `setting_sources=["project"]` |
| קונטקסט | `context.py`: system קבוע + `<memory>` + סיכום (אם היה) + הטקסט | Claude Code מוסיף לבד את CLAUDE.md המלא ואת ההקשר שלו |
| compaction | `compaction.py`: מעל הסף (12,000 טוקנים בתרחיש) מסכם את כל השיחה | אוטומטי |
| caching | `caching.py`: 3 breakpoints (הכלי האחרון, system, הבלוק האחרון בהודעה האחרונה) | אוטומטי |
| טוקנים | `tokens.py`: usage ועלות לכל קריאה ולכל תור | `ResultMessage.usage` + `total_cost_usd` |

בגרסת ה-API כל פעולה בזמן ריצה מודפסת עם שם הקובץ שביצע אותה, למשל `[loop.py] stop_reason=tool_use` או `[memory.py] retrieved keys=['diet','allergies'] skipped=['favorites']`.

## 3. תרחיש ובדיקות

`scenario.json`: 7 פניות בשני סשנים. סשן 2 רץ על מופע **חדש** של הסוכן עם שיחה חדשה. הגשר היחיד בין הסשנים הוא הזיכרון שעל הדיסק.

| תור | פנייה | מה זה בודק |
|---|---|---|
| s1t1 | אני צמחונית ואלרגית לבוטנים, תזכור | שמירה לזיכרון |
| s1t2 | ארוחת ערב בפחות מ-30 דק' | שימוש בכלים + סינון לפי הזיכרון |
| s1t3 | חפש ברשת שקשוקה | **כלי חיצוני** (TheMealDB) |
| s1t4 | אבשל את r01, הוסף לרשימת קניות ושמור כמועדף | כלי קבצים + זיכרון |
| s2t1 | מה אתה זוכר עליי? | **שליפה מהזיכרון בסשן 2** |
| s2t2 | התחלתי לאכול דגים, עדכן והצע דג | **סתירה למשהו שנשמר** |
| s2t3 | מה ברשימת הקניות? | מצב שנשמר לקובץ |

8 בדיקות pass/fail. חמש מהן (C1 עד C5) בודקות את **המצב שנשמר בדיסק** (`memory.json`, `shopping_list.json`), ולא את טקסט התשובה. C6 בודקת את מעקב הכלים, ו-C7 ו-C8 בודקות את התשובה (C8 היא בדיקת בטיחות: לא הוצע מתכון עם בוטנים).

## 4. תוצאות

> הטבלאות נוצרות אוטומטית מ-`results/*.json` על ידי `python compare.py`.

<!-- TABLES:START -->
### API מול SDK (כל התרחיש, 7 פניות, 2 סשנים)

| מדד | API | SDK |
|---|---|---|
| input (לא מ-cache) | לא הורץ עדיין | 40 |
| cache read | לא הורץ עדיין | 51,008 |
| cache write | לא הורץ עדיין | 3,482 |
| output | לא הורץ עדיין | 2,232 |
| אחוז cache (read מתוך כל ה-input) | לא הורץ עדיין | 93.5% |
| קריאות למודל | לא הורץ עדיין | 15 |
| עלות כוללת | לא הורץ עדיין | $0.0831 |
| זמן כולל | לא הורץ עדיין | 62.09s |
| בדיקות שעברו | לא הורץ עדיין | 8/8 |

### לפי תור

| תור | API in/read/write/out | API קריאות | API כלים | API עלות | SDK in/read/write/out | SDK קריאות | SDK כלים | SDK עלות |
|---|---|---|---|---|---|---|---|---|
| s1t1 | - | - | - | - | 4/5451/0/238 | 2 | save_memory, save_memory | $0.0060 |
| s1t2 | - | - | - | - | 8/9312/795/524 | 3 | search_recipes, search_recipes | $0.0187 |
| s1t3 | - | - | - | - | 8/11829/1009/489 | 3 | search_web_recipes, get_recipe | $0.0203 |
| s1t4 | - | - | - | - | 6/9662/631/266 | 2 | add_to_shopping_list, save_memory | $0.0123 |
| s2t1 | - | - | - | - | 2/2612/0/166 | 1 | - | $0.0040 |
| s2t2 | - | - | - | - | 6/5422/527/379 | 2 | save_memory, search_recipes | $0.0129 |
| s2t3 | - | - | - | - | 6/6720/520/170 | 2 | get_shopping_list | $0.0089 |

### שורות קוד לכל חלק ב-harness

API = שורות קוד (בלי הערות ושורות ריקות) ב-`API/harness/<part>.py`. SDK = שורות שמסומנות `# replaces: <part>` ב-`SDK/`.

| חלק | API | SDK |
|---|---|---|
| loop | 44 | 4 |
| tools | 89 | 18 |
| history | 42 | 6 |
| memory | 36 | 8 |
| context | 23 | 2 |
| compaction | 51 | 1 |
| caching | 22 | 1 |
| tokens | 39 | 13 |
| **סה"כ** | **346** | **53** |

### בדיקות

| בדיקה | תיאור | API | SDK |
|---|---|---|---|
| C1 | allergy saved to memory (state) | - | ✅ |
| C2 | contradiction resolved: diet is now pescatarian (state) | - | ✅ |
| C3 | old decision kept in history vegetarian -> pescatarian (state) | - | ✅ |
| C4 | favorite saved (state) | - | ✅ |
| C5 | recipe ingredients on the shopping list file (state) | - | ✅ |
| C6 | external tool used for the online search | - | ✅ |
| C7 | session 2 recalls diet and allergy from memory | - | ✅ |
| C8 | fish suggestion respects the peanut allergy | - | ✅ |
<!-- TABLES:END -->

## 5. ניתוח

### איפה ה-SDK עלה יותר טוקנים ואיפה פחות, ולמה?

**יותר:**
- **בסיס קבוע גדול יותר.** גם עם system prompt משלי, Claude Code מוסיף הקשר משלו: את CLAUDE.md עטוף בהוראות שלו, מידע על הסביבה ואת סכמות כלי ה-MCP עם הקידומת `mcp__chef__`. בתור s2t1 (קריאה אחת, בלי כלים) ה-SDK שלח כ-2,600 טוקני input, בעוד שהטקסט שלי (system, 7 כלים, זיכרון והודעה) הוא בערך 1,200 טוקנים. ההפרש הוא מה ש-Claude Code מוסיף לבד.
- **כל הזיכרון בכל תור.** CLAUDE.md נטען במלואו, כולל favorites ו-notes, גם כשהשאלה לא קשורה אליהם. ב-API, `memory.py` מסנן.
- **כתיבת cache יקרה יותר.** Claude Code כותב cache עם TTL של שעה, שעולה 2x ממחיר input (8$ למיליון). ה-API שלי משתמש ב-TTL של 5 דקות, שעולה 1.25x (5$ למיליון). וידאתי את זה: העלות ש-`total_cost_usd` מדווח מתאימה בדיוק לחישוב עם 8$ למיליון על cache write.

**פחות / שווה:**
- **אחוז cache גבוה מאוד** (93.5% ב-SDK) בלי לכתוב שורה. ה-SDK מנהל את ה-breakpoints בעצמו.
- **TTL של שעה משתלם בין ריצות.** בריצה השנייה ה-cache מהריצה הראשונה עוד היה חם, ולכן s1t1 היה כולו cache read (0 write). "מצב נקי" בדיסק לא מנקה את ה-cache בשרת.
- **אין קריאת compaction**, כי השיחות קצרות מתחת לסף האוטומטי. ב-API הגדרתי סף נמוך (12K) כדי להדגים את המנגנון, וזה עלול להוסיף קריאת סיכום אחת.

### על מה הייתה לי שליטה ב-API ואיבדתי ב-SDK?

1. **מה נכנס לקונטקסט.** ב-API אני מחליטה בדיוק אילו עובדות זיכרון נכנסות לכל תור. ב-SDK, CLAUDE.md נכנס כולו, ו-Claude Code מוסיף הקשר שאני לא רואה ולא שולטת בו.
2. **Caching.** ב-API אני בוחרת איפה ה-breakpoints ומה ה-TTL. ב-SDK זה קבוע, כולל TTL של שעה שעולה יותר בכתיבה.
3. **Compaction.** ב-API אני קובעת את הסף, את פרומפט הסיכום ואת מה שנשמר אחריו (בלי בלוקי thinking ישנים). ב-SDK זה אוטומטי.
4. **פורמט תוצאות הכלים.** ב-API ה-`tool_result` הוא בדיוק מה שאני שולחת. ב-SDK הוא עובר דרך שכבת MCP.
5. **מדידה מדויקת.** ב-API יש לי usage לכל קריאה. ב-SDK יש סיכום לכל תור, ו-`total_cost_usd` **מצטבר** לאורך סשן שעושה resume. בהתחלה זה הטעה אותי (העלות נראתה גבוהה פי 3), עד שחישבתי את ההפרש בין תורות.
6. **Latency.** כל תור ב-SDK מפעיל תהליך CLI חדש, וזה מוסיף כמה שניות לכל תור.

**מה ה-SDK חסך לי:** לולאה, dispatch, שגיאות, היסטוריה, caching, compaction ומדידת עלות. בערך 350 שורות קוד בחלקי ה-harness הפכו לכ-50 שורות הגדרה (ראו טבלת שורות הקוד), ואין לי באגים לתחזק בקוד הזה.

### איזו גרסה הייתי בוחרת לסוכן הזה, ולמה?

**את גרסת ה-API.** ChefScout הוא סוכן קטן (7 כלים, שיחות קצרות) שרץ הרבה פעמים, והערך שלו הוא בדיוק בשליטה בקונטקסט: אלרגיה היא עובדת בטיחות שחייבת להיכנס לכל תור, ושאר הזיכרון צריך להישאר בחוץ כשהוא לא רלוונטי. ב-API אני משלמת רק על מה שאני שולחת, רואה כל קריאה ובוחרת TTL זול. היתרונות הגדולים של ה-SDK (כלי קבצים ו-Bash מובנים, subagents, ניהול שיחות ארוכות) לא נחוצים לסוכן הזה, ובפועל כיביתי אותם (`tools=[]`).

ה-SDK מצוין לאב-טיפוס: בניתי אותו מהר יותר, הוא עבר את כל הבדיקות, והוא עדיף לסוכן שצריך לעבוד עם קבצים וקוד.

## 6. הרצה

```powershell
pip install -r requirements.txt          # גרסאות נעולות
python -m pytest -q                      # בדיקות offline, בלי מפתח
# API: המפתח רק כמשתנה סביבה בטרמינל, לעולם לא בקוד או ב-git
$env:ANTHROPIC_API_KEY = "sk-ant-..."
python API/main.py --scenario scenario.json --out results/api.json
Remove-Item Env:ANTHROPIC_API_KEY        # ה-SDK רץ על ה-login של Claude Code
python SDK/main.py --scenario scenario.json --out results/sdk.json
python compare.py                        # מעדכן את הטבלאות בדוח
```

כל ריצה מוחקת את `state/<api|sdk>/` ומתחילה ממצב נקי.
