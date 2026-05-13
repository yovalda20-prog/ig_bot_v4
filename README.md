[Instagram_Bot_v4_Guide.html](https://github.com/user-attachments/files/27727553/Instagram_Bot_v4_Guide.html)

<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="UTF-8">
    <style>
        @page {
            size: A4;
            margin: 15mm;
        }
        body {
            font-family: Arial, sans-serif;
            line-height: 1.5;
            color: #2c3e50;
            margin: 0;
            padding: 0;
            background-color: #f4f7f6;
        }
        .container {
            background-color: #ffffff;
            padding: 30px;
            border-radius: 8px;
        }
        .header {
            background-color: #8e44ad;
            color: white;
            padding: 30px;
            text-align: center;
            margin: -15mm -15mm 20px -15mm;
            border-bottom: 4px solid #2ecc71;
        }
        h1 { margin: 0; font-size: 26pt; }
        h2 { color: #8e44ad; border-bottom: 2px solid #ddd; padding-bottom: 8px; margin-top: 25px; }
        h3 { color: #2980b9; margin-top: 15px; }
        .code-block {
            background-color: #2d3436;
            color: #dfe6e9;
            padding: 15px;
            border-radius: 5px;
            font-family: 'Courier New', monospace;
            direction: ltr;
            text-align: left;
            font-size: 10pt;
            margin: 10px 0;
        }
        .important-box {
            background-color: #fff3cd;
            border: 1px solid #ffeeba;
            color: #856404;
            padding: 15px;
            margin: 20px 0;
            border-right: 5px solid #ffc107;
        }
        ul { margin-right: 20px; }
        .footer {
            margin-top: 40px;
            font-size: 9pt;
            color: #95a5a6;
            text-align: center;
            border-top: 1px solid #eee;
            padding-top: 10px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Instagram Growth Bot v4.0</h1>
        <p>Documentation & Terms of Use</p>
    </div>

    <div class="container">
        <h2>1. דרישות מערכת וסביבת עבודה</h2>
        <p>לפני הרצת הבוט, יש לוודא שהסביבה מוגדרת כראוי:</p>
        <h3>התקנת ספריות Python:</h3>
        <div class="code-block">
            pip install undetected-chromedriver selenium anthropic requests
        </div>
        <h3>דרישות נוספות:</h3>
        <ul>
            <li><strong>Chrome Browser:</strong> מומלץ להשתמש בגרסה האחרונה. הקוד מכוון לבינארי בנתיב <code>/usr/bin/google-chrome</code>.</li>
            <li><strong>SQLite3:</strong> מובנה ב-Python, משמש לניהול היסטוריית ביקורים ומניעת כפילויות.</li>
            <li><strong>Anthropic API Key:</strong> (אופציונלי) עבור מנגנון AI XPath Recovery לתיקון כפתורים שנשברו.</li>
        </ul>

        <h2>2. הגדרות ראשוניות (Configuration)</h2>
        <p>יש לערוך את המשתנים הבאים בתוך הקוד לפני ההפעלה:</p>
        <ul>
            <li><code>USERNAME</code> / <code>PASSWORD</code>: פרטי החשבון שלך.</li>
            <li><code>SEED_PROFILE</code>: הפרופיל ממנו הבוט יתחיל "לדוג" עוקבים פוטנציאליים.</li>
            <li><code>CHROME_PROFILE_PATH</code>: נתיב לשמירת הפרופיל (Cookies) כדי למנוע התחברות מחדש בכל פעם.</li>
        </ul>

        <div class="important-box">
            <strong>שים לב:</strong> הבוט כולל מצב <code>DEBUG_MODE</code>. כאשר הוא מופעל (True), זמני ההמתנה מתקצרים משמעותית. לשימוש אמיתי, יש להעביר ל-False.
        </div>

        <h2>3. מצבי פעולה</h2>
        <ul>
            <li><strong>Follow אוטומטי:</strong> סריקת פרופילים לפי פילטרים (כמות עוקבים, יחס RR) וביצוע Follow.</li>
            <li><strong>Scout:</strong> איסוף נתונים בלבד ויצירת דוח TXT ללא ביצוע פעולות.</li>
            <li><strong>Manual Follow:</strong> קריאת רשימת משתמשים מקובץ חיצוני וסינון שלהם.</li>
            <li><strong>Cleanup (Unfollow):</strong> בדיקת מי מהנעקבים לא חזר לעקוב אחרי תקופת זמן והסרת עוקב.</li>
        </ul>

        <h2>4. הגנה על החשבון (OPSEC & Safety)</h2>
        <p>הבוט משתמש בטכניקות מתקדמות למניעת חסימות:</p>
        <ul>
            <li><strong>Human Simulation:</strong> הזזת עכבר אקראית, גלילה (Scroll) אנושית וזמני שהייה (Dwell time).</li>
            <li><strong>RR Self-Health Check:</strong> עצירה אוטומטית אם יחס העוקבים/נעקבים של החשבון שלך חוצה את הרף המותר.</li>
            <li><strong>Daily Limits:</strong> הגבלה קשיחה של כמות פעולות ביום (ברירת מחדל: 25).</li>
        </ul>

        <h2>5. תנאי שימוש והצהרת אחריות</h2>
        <p>השימוש בכלי זה כפוף לתנאים הבאים:</p>
        <ol>
            <li>הכלי נועד למטרות מחקר ולימוד בלבד.</li>
            <li><strong>אחריות המשתמש:</strong> המשתמש נושא באחריות המלאה לכל נזק, חסימת חשבון או הפרה של תנאי השימוש של Instagram/Meta.</li>
            <li>אין להשתמש בכלי זה לביצוע ספאם, הטרדה או כל פעולה הפוגעת במשתמשים אחרים.</li>
        </ol>

        <div class="footer">
            Developed by Yuval David | Instagram Automation Toolset 2026
        </div>
    </div>
</body>
</html>
