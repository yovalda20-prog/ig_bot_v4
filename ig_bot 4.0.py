"""
Instagram Growth Bot — v2.0 (Refactored)
=========================================
Modes  : Auto-Follow | Scout | Manual
Extras : AI-assisted XPath recovery (Anthropic), SQLite visit log,
         human-behaviour simulation, RR self-health checks.
"""

# ─── Standard library ─────────────────────────────────────────────────────────
import json
import logging
import random
import re
import sqlite3
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

# ─── Third-party ──────────────────────────────────────────────────────────────
import undetected_chromedriver as uc
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
import re  # וודא שיש לך גם את זה בשביל ה-parse_count שסידרנו


# ═══════════════════════════════════════════════════════════════════════════════
#  LOGGING
# ═══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
#  CONFIG  — edit these before running
# ═══════════════════════════════════════════════════════════════════════════════

USERNAME = "ido.lifestyle.2026.deafness067@aleeas.com"
PASSWORD = """f_kA"):'C*f4'u" """
SEED_PROFILE = "yuvaldavid2"

# Self-health RR thresholds (own-account following/followers ratio)
RR_MIN_THRESHOLD = 1.2
RR_MAX_THRESHOLD = 1.8

# ──── DEVELOPER SETTINGS ──────────────────────────────────────────────────────
DEBUG_MODE = True  # שנה ל-False כשאתה מריץ "על אמת"
# תיקייה שתשמור את החיבור שלך לאינסטגרם
CHROME_PROFILE_PATH = str(Path.home() / "IG_Bot_Dev_Profile")


SESSION_DIR = str(Path.home() / "IG_Bot_Chrome_Profile")
DB_PATH = "backup_scripts+DB/ig_bot.db"
SCOUT_REPORT_PATH = "scout_report.txt"
MANUAL_OUTPUT_PATH = "filtered_users.txt"
XPATH_CACHE_FILE = "xpath_cache.json"

# הגדרות חדשות למצב Cleanup (v4.0)
UNFOLLOW_AFTER_DAYS = 7
MAX_UNFOLLOWS_PER_RUN = 25
MANUAL_OUTPUT_PATH = "filtered_users.txt"
XPATH_CACHE_FILE = "xpath_cache.json"

# ── Anthropic API key — leave empty ("") to disable AI XPath recovery ─────────
ANTHROPIC_API_KEY = ""  # Disabled — paste your key here to enable
# ─────────────────────────────────────────────────────────────────────────────

BATCH_SIZE = 10
MAX_FOLLOWS_PER_DAY = 25
REVISIT_DAYS = 30

# Audience filter thresholds
FILTER_MIN_FOLLOWERS = 300
FILTER_MAX_FOLLOWING = 2000
FILTER_RR_MIN = 1.0
FILTER_RR_MAX = 5.0

# Timing (seconds)
DWELL_TIME_RANGE = (35, 55)
WAIT_BETWEEN_USERS = (5, 6)
WAIT_BETWEEN_BATCHES = (20 * 60, 40 * 60)

COFFEE_BREAK_CHANCE = 0.10
COFFEE_BREAK_RANGE = (20, 21)

# ═══════════════════════════════════════════════════════════════════════════════
#  XPATH FALLBACK LISTS
# ═══════════════════════════════════════════════════════════════════════════════

# User-identified precise selector goes FIRST for fastest resolution.
FOLLOW_XPATHS = [
    "//button[contains(@class, '_aswp') and .//div[text()='Follow']]",  # precise
    "//button[normalize-space(text())='Follow']",
    "//button[normalize-space()='Follow']",
    "//button[.//div[normalize-space()='Follow']]",
    "//*[@role='button'][normalize-space()='Follow']",
    "//button[contains(@aria-label,'Follow') and not(contains(@aria-label,'Following'))]",
    "//div[contains(text(),'Follow')]/ancestor::button",
]

FOLLOWING_CHECK_XPATHS = [
    "//button[normalize-space(text())='Following' or normalize-space(text())='Requested']",
    "//button[normalize-space()='Following' or normalize-space()='Requested']",
    "//*[@role='button'][normalize-space()='Following']",
] 

FOLLOWERS_YOU_XPATHS = [
    # Instagram shows "Follows you" badge next to the username on their profile
    "//*[normalize-space(text())='Follows you']",
    "//*[normalize-space(text())='עוקב אחריך']",          # Hebrew
    "//*[contains(@class,'_aayn') and contains(.,'Follows you')]",
    "//span[contains(normalize-space(),'Follows you')]",
    # Fallback: the mutual-friends / "followed by" sub-text
    "//*[contains(normalize-space(),'followed by')]",
]

UNFOLLOW_CONFIRM_XPATHS = [
    "//button[normalize-space(text())='Unfollow']",
    "//button[normalize-space()='Unfollow']",
    "//*[@role='button'][normalize-space()='Unfollow']",
    "//button[normalize-space(text())='הפסק לעקוב']",    # Hebrew
    "//div[@role='dialog']//button[contains(normalize-space(),'Unfollow')]",
]

SUGGESTED_XPATHS = [
    "//div[@role='button' and .//*[name()='svg']]",
    "[preceding::button[normalize-space()='Follow'] or "
    "following::button[normalize-space()='Follow']][1]",
    "//header//*[@role='button'][.//*[name()='svg']][not(normalize-space()='Follow')][1]",
    "//button[normalize-space()='Follow']/following-sibling::*[@role='button'][1]",
    "//*[name()='svg'][@height='16' or @height='12']"
    "[contains(@viewBox,'24')]/ancestor::*[@role='button'][1]",
]

# Stage-1 XPaths for get_suggested_users (the "Discover people" icon)
_SUGGEST_ICON_XPATHS = [
    # ה-XPath החדש מבוסס על ה-SVG ששלחת
    "//div[@role='button'][.//svg[@aria-label='Similar accounts' or @aria-label='חשבונות דומים']]",
    "//div[@role='button'][.//svg[@aria-label='Discover people' or @aria-label='גילוי אנשים']]",
    "//header//section/div/div/div/div/div[3]/div[@role='button']",
    "//div[button[contains(.,'Message') or contains(.,'הודעה')]]/following-sibling::div//div[@role='button']",
]

# ═══════════════════════════════════════════════════════════════════════════════
#  STARTUP MENU
# ═══════════════════════════════════════════════════════════════════════════════

def startup_menu() -> dict:
    """Interactive CLI menu; returns a config dict consumed by run()."""
    print("\n" + "=" * 55)
    print("        Instagram Bot — הגדרות הפעלה (v4.0)")
    print("=" * 55)

    print("\n📋 מצב פעולה:")
    print("  1. Follow אוטומטי  — הבוט עוקב לבד לפי הפילטרים")
    print("  2. Scout בלבד      — סורק ושומר דוח TXT, בלי follow")
    print("  3. Follow ידני     — קורא TXT, מסנן, ואתה עוקב ידנית")
    print("  4. Cleanup / Unfollow — בודק מי לא עקב בחזרה ומבטל עוקב")

    while True:
        mode = input("\nבחר מצב (1/2/3/4): ").strip()
        if mode in ("1", "2", "3", "4"):
            break
        print("❌  בחר 1, 2, 3 או 4")

    txt_path = None
    if mode == "3":
        txt_path = input("\n📄 נתיב לקובץ TXT עם יוזרנריים: ").strip()
        if not Path(txt_path).exists():
            print(f"❌  קובץ לא נמצא: {txt_path}")
            sys.exit(1)

    config = {
        "mode": {"1": "follow", "2": "scout", "3": "manual", "4": "cleanup"}[mode],
        "txt_path": txt_path,
    }

    print("\n" + "=" * 55)
    print(f"  ✅  מצב      : {config['mode'].upper()}")
    if txt_path:
        print(f"  ✅  קובץ TXT : {txt_path}")
    print("=" * 55 + "\n")
    time.sleep(1)
    return config


# ═══════════════════════════════════════════════════════════════════════════════
#  AI XPATH RECOVERY
# ═══════════════════════════════════════════════════════════════════════════════

_ai_client = None


def _get_ai_client():
    """Lazy-init the Anthropic client; returns None if key is absent or import fails."""
    global _ai_client
    if _ai_client is None:
        if not ANTHROPIC_API_KEY:
            log.warning("ANTHROPIC_API_KEY is empty — AI XPath recovery disabled.")
            return None
        try:
            import anthropic  # noqa: PLC0415
            _ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        except Exception as exc:
            log.error(f"AI client init failed: {exc}")
    return _ai_client


def _load_xpath_cache() -> dict:
    try:
        return json.loads(Path(XPATH_CACHE_FILE).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_xpath_cache(cache: dict) -> None:
    Path(XPATH_CACHE_FILE).write_text(
        json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _ai_find_xpath(driver: uc.Chrome, goal: str) -> str | None:
    """
    Send a screenshot to Claude and request a working XPath.
    Only called when all manual XPaths AND the cache have failed.
    """
    client = _get_ai_client()
    if not client:
        return None

    log.info(f"🤖  AI מחפש XPath עבור: '{goal}'")
    try:
        screenshot_b64 = driver.get_screenshot_as_base64()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                f'Look at this Instagram screenshot.\n'
                                f'Find the element: "{goal}"\n'
                                f'Return ONLY valid JSON, nothing else:\n'
                                f'{{"xpath": "//button[...]", "found": true}}\n'
                                f'or if not found:\n'
                                f'{{"found": false}}\n'
                                f'The XPath must be usable with Selenium find_element.'
                            ),
                        },
                    ],
                }
            ],
        )
        result = json.loads(response.content[0].text)
        if result.get("found"):
            log.info(f"🤖  AI מצא XPath: {result['xpath']}")
            return result["xpath"]
    except Exception as exc:
        log.warning(f"AI XPath error: {exc}")
    return None


def smart_find(
    driver: uc.Chrome,
    goal: str,
    fallback_xpaths: list[str],
    ai_enabled: bool = False,
    timeout: int = 4,
):
    """
    Three-stage element locator:
      1. Manual XPath list (fast, free)
      2. Cached XPath from previous AI run
      3. AI screenshot→XPath (only when ai_enabled=True and stages 1–2 failed)

    The AI result is written to cache so it won't be queried again until it breaks.
    Returns a WebElement or None.
    """
    # Stage 1 — manual list
    for xpath in fallback_xpaths:
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            return el
        except TimeoutException:
            continue

    # Stage 2 — cache
    cache = _load_xpath_cache()
    if goal in cache:
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, cache[goal]))
            )
            log.info("✅  נמצא מ-cache")
            return el
        except TimeoutException:
            log.warning("⚠️  XPath מה-cache נכשל — מוחק ומנסה AI")
            del cache[goal]
            _save_xpath_cache(cache)

    # Stage 3 — AI
    if ai_enabled:
        xpath = _ai_find_xpath(driver, goal)
        if xpath:
            cache[goal] = xpath
            _save_xpath_cache(cache)
            try:
                return driver.find_element(By.XPATH, xpath)
            except Exception:
                pass

    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  DATABASE (SQLite) - v4.0 Status-Based System
# ═══════════════════════════════════════════════════════════════════════════════

# הגדרת סטטוסים לניהול המשתמשים
STATUS_SCANNED     = "SCANNED"
STATUS_FOLLOWED    = "FOLLOWED"
STATUS_FRIEND      = "FRIEND"
STATUS_UNFOLLOWED  = "UNFOLLOWED"

def db_connect() -> sqlite3.Connection:
    """פותח את ה-DB ומבצע הגירה מהמבנה הישן לחדש באופן אוטומטי."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # בדיקה אם קיימת הטבלה הישנה 'visited'
    legacy = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='visited'"
    ).fetchone()
    
    if legacy:
        # משנים את שם הטבלה הישנה לגיבוי כדי לא לאבד נתונים
        try:
            conn.execute("ALTER TABLE visited RENAME TO _visited_legacy")
            conn.commit()
            log.info("Legacy `visited` table preserved as `_visited_legacy`.")
        except Exception:
            pass

    # יצירת הטבלה החדשה והחכמה
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users_status (
            username          TEXT      PRIMARY KEY,
            status            TEXT      NOT NULL DEFAULT 'SCANNED',
            last_action_date  DATETIME  NOT NULL DEFAULT (datetime('now')),
            notes             TEXT
        )
        """
    )
    conn.commit()
    return conn

def db_upsert_user(conn: sqlite3.Connection, username: str, status: str, notes: str | None = None) -> None:
    """הפונקציה המרכזית: מעדכנת מצב של משתמש (למשל מ-'סרוק' ל-'נעקב')."""
    if notes is not None:
        conn.execute(
            """
            INSERT INTO users_status (username, status, last_action_date, notes)
            VALUES (?, ?, datetime('now'), ?)
            ON CONFLICT(username) DO UPDATE SET
                status           = excluded.status,
                last_action_date = excluded.last_action_date,
                notes            = excluded.notes
            """,
            (username, status, notes),
        )
    else:
        conn.execute(
            """
            INSERT INTO users_status (username, status, last_action_date)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(username) DO UPDATE SET
                status           = excluded.status,
                last_action_date = excluded.last_action_date
            """,
            (username, status),
        )
    conn.commit()

def db_was_visited_recently(conn: sqlite3.Connection, username: str) -> bool:
    """בודק אם כבר טיפלנו ביוזר הזה ב-X הימים האחרונים."""
    row = conn.execute(
        "SELECT 1 FROM users_status WHERE username = ? "
        "AND last_action_date > datetime('now', ?)",
        (username, f"-{REVISIT_DAYS} days"),
    ).fetchone()
    return row is not None

def db_follows_today(conn: sqlite3.Connection) -> int:
    """סופר כמה Follow ביצענו היום כדי לא לחרוג מהמכסה."""
    row = conn.execute(
        "SELECT COUNT(*) FROM users_status "
        "WHERE status = ? AND date(last_action_date) = date('now')",
        (STATUS_FOLLOWED,),
    ).fetchone()
    return row[0] if row else 0

def db_get_random_followed(conn: sqlite3.Connection) -> str:
    """בוחר משתמש אקראי שעקבנו אחריו כדי למצוא דרכו עוד אנשים."""
    try:
        row = conn.execute(
            "SELECT username FROM users_status "
            "WHERE status = ? ORDER BY RANDOM() LIMIT 1",
            (STATUS_FOLLOWED,),
        ).fetchone()
        return row["username"] if row else SEED_PROFILE
    except Exception:
        return SEED_PROFILE

def db_get_unfollow_candidates(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """גרסת בדיקה: שולף את 2 האנשים הראשונים שעקבנו אחריהם, בלי קשר לזמן."""
    rows = conn.execute(
        "SELECT username, last_action_date, notes FROM users_status "
        "WHERE status = ? "
        "ORDER BY last_action_date ASC LIMIT 2",
        (STATUS_FOLLOWED,)
    ).fetchall()
    return rows

# ═══════════════════════════════════════════════════════════════════════════════
#  SCOUT REPORT
# ═══════════════════════════════════════════════════════════════════════════════


def scout_report_header() -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(SCOUT_REPORT_PATH, "a", encoding="utf-8") as fh:
        fh.write(f"\n{'─' * 80}\n")
        fh.write(f"Scout run started: {ts}  |  Seed: {SEED_PROFILE}\n")
        fh.write(f"{'─' * 80}\n")


def scout_report_write(
    username: str,
    followers: int,
    rr: float,
    private: bool,
    last_post: str,
) -> None:
    line = (
        f"https://www.instagram.com/{username} | "
        f"Followers: {followers:,} | "
        f"RR: {rr:.2f} | "
        f"Private: {'Yes' if private else 'No'} | "
        f"Last Post: {last_post}"
    )
    log.info(f"[SCOUT] {line}")
    with open(SCOUT_REPORT_PATH, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


# ═══════════════════════════════════════════════════════════════════════════════
#  DRIVER
# ═══════════════════════════════════════════════════════════════════════════════

def build_driver() -> uc.Chrome:
    """Starts undetected-chromedriver with a persistent user profile."""
    options = uc.ChromeOptions()
    
    # התיקון הקריטי: הגדרת הנתיב המדויק לכרום המעודכן (148)
    # וודא שהנתיב הזה הוא מה שקיבלת בפקודה which google-chrome
    options.binary_location = "/usr/bin/google-chrome"
    
    # שימוש בפרופיל קבוע כדי לשמור התחברות (Cookies)
    options.add_argument(f"--user-data-dir={CHROME_PROFILE_PATH}")
    
    # הגדרות למניעת חלונות קופצים של כרום בהפעלה ראשונה
    options.add_argument("--no-first-run")
    options.add_argument("--no-service-autorun")
    options.add_argument("--password-store=basic")
    
    # הגדרות ביצועים (אופציונלי - עוזר ליציבות)
    options.add_argument("--window-size=1366,768")

    try:
        # עכשיו ה-driver ידע ללכת ישר לגרסה 148 בנתיב שהגדרנו למעלה
        driver = uc.Chrome(options=options, headless=False)
        log.info(f"Driver started with persistent profile: {CHROME_PROFILE_PATH}")
        return driver
    except Exception as e:
        log.error(f"Failed to start Chrome: {e}")
        sys.exit(1)



# ═══════════════════════════════════════════════════════════════════════════════
#  HUMAN SIMULATION
# ═══════════════════════════════════════════════════════════════════════════════


def human_sleep(min_s: float, max_s: float) -> None:
    global DEBUG_MODE  # <--- להוסיף את זה
    if DEBUG_MODE:
        time.sleep(0.5)
        return
    
    duration = random.uniform(min_s, max_s)
    log.info(f"Sleeping {duration:.1f}s...")
    time.sleep(duration)

def maybe_coffee_break() -> None:
    global DEBUG_MODE
    if DEBUG_MODE:
        return # במצב מפתח אין הפסקות קפה
        
    if random.random() < 0.08:
        break_min = random.uniform(*COFFEE_BREAK_RANGE)
        log.info(f"☕ Coffee break ({break_min:.1f} min)...")
        time.sleep(break_min * 60)


def dwell(username: str) -> None:
    seconds = random.uniform(*DWELL_TIME_RANGE)
    log.info(f"Dwelling {seconds:.1f}s on @{username} profile...")
    time.sleep(seconds)


def jitter_mouse(driver: uc.Chrome) -> None:
    try:
        actions = ActionChains(driver)
        for _ in range(random.randint(3, 7)):
            actions.move_by_offset(
                random.randint(-120, 120), random.randint(-80, 80)
            )
            actions.pause(random.uniform(0.05, 0.2))
        actions.perform()
    except Exception:
        pass


def human_scroll(driver: uc.Chrome) -> None:
    for _ in range(random.randint(3, 6)):
        delta = random.randint(150, 550) * random.choice([1, -1])
        driver.execute_script(
            f"window.scrollBy({{top:{delta}, behavior:'smooth'}});"
        )
        jitter_mouse(driver)
        time.sleep(random.uniform(0.4, 1.8))
        if random.random() < 0.3:
            time.sleep(random.uniform(0.8, 2.2))


def type_humanly(element, text: str) -> None:
    for char in text:
        element.send_keys(char)
        human_sleep(0.04, 0.19)


def safe_click(driver: uc.Chrome, element) -> bool:
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", element
        )
        human_sleep(0.3, 0.9)
        jitter_mouse(driver)
        human_sleep(0.1, 0.3)
        element.click()
        return True
    except ElementClickInterceptedException:
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception:
            return False
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  LOGIN
# ═══════════════════════════════════════════════════════════════════════════════


def is_logged_in(driver: uc.Chrome) -> bool:
    driver.get("https://www.instagram.com/")
    human_sleep(3, 5)
    return "accounts/login" not in driver.current_url


def handle_2fa_or_challenge(driver: uc.Chrome) -> bool:
    indicators = [
        "//input[@name='verificationCode']",
        "//input[contains(@aria-label,'ecurity')]",
        "//h2[contains(text(),'Two-Factor')]",
        "//h2[contains(text(),'Verify')]",
        "//p[contains(text(),'verification code')]",
        "//p[contains(text(),'suspicious')]",
    ]
    for xpath in indicators:
        try:
            driver.find_element(By.XPATH, xpath)
            log.warning("=" * 60)
            log.warning("⚠  2FA / CHALLENGE detected.")
            log.warning("   Complete verification manually in the browser window.")
            log.warning("   Press ENTER in this terminal when done.")
            log.warning("=" * 60)
            input()
            human_sleep(3, 5)
            return True
        except NoSuchElementException:
            pass
    return False


def dismiss_dialogs(driver: uc.Chrome) -> None:
    for xpath in [
        "//button[contains(text(),'Not Now')]",
        "//button[contains(text(),'Later')]",
        "//button[contains(text(),'Skip')]",
        "//button[contains(text(),'Allow')]",
    ]:
        try:
            btn = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            btn.click()
            human_sleep(0.8, 1.8)
        except TimeoutException:
            pass


def manual_login_wait(driver):
    """פתח את אינסטגרם וחכה שהמשתמש יתחבר ידנית"""
    driver.get("https://www.instagram.com/accounts/login/")
    log.info("!!! פעולה נדרשת !!!")
    log.info("אנא בצע התחברות ידנית בחלון הכרום שנפתח.")
    log.info("סיים את כל אימותי האבטחה (מייל/SMS/2FA) עד שתראה את הפיד.")
    
    # הקוד יעצור כאן ולא ימשיך עד שתלחץ אנטר בטרמינל
    input("\n===> אחרי שהתחברת ואתה רואה את הפיד, לחץ ENTER כאן כדי להתחיל את הבוט: ")
    
    log.info("התחברות אושרה. מתחיל אוטומציה...")
    dismiss_dialogs(driver) # מנקה פופ-אפים של "שמור סיסמה" או "התראות"
# ═══════════════════════════════════════════════════════════════════════════════
#  PRIVATE ACCOUNT DETECTION & LAST POST DATE
# ═══════════════════════════════════════════════════════════════════════════════

_PRIVATE_PHRASES = [
    "this account is private",
    "follow to see their photos",
    "follow this account to see",
]


def is_private(driver: uc.Chrome) -> bool:
    try:
        driver.find_element(
            By.XPATH,
            "//*[contains("
            "translate(normalize-space(text()),"
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
            "'abcdefghijklmnopqrstuvwxyz'),"
            "'this account is private')]",
        )
        return True
    except NoSuchElementException:
        pass

    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        if any(phrase in page_text for phrase in _PRIVATE_PHRASES):
            return True
    except Exception:
        pass

    try:
        driver.find_element(By.XPATH, "//article")
        return False
    except NoSuchElementException:
        pass

    try:
        driver.find_element(
            By.XPATH,
            "//*[@aria-label='Private account' or @aria-label='Private']",
        )
        return True
    except NoSuchElementException:
        pass

    return False


def get_last_post_date(driver: uc.Chrome) -> str:
    try:
        time_el = driver.find_element(
            By.XPATH,
            "(//article//time[@datetime] | //main//time[@datetime])[1]",
        )
        raw = time_el.get_attribute("datetime") or ""
        if raw:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
    except NoSuchElementException:
        pass
    except Exception as exc:
        log.debug(f"last_post_date parse error: {exc}")
    return "N/A"


# ═══════════════════════════════════════════════════════════════════════════════
#  PROFILE STATS  — single canonical implementation
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_count(text: str) -> int:
    """
    Convert Instagram display strings (e.g. '12.4K', '2M', '1,234 followers') to int.
    Handles Hebrew and English text safely.
    """
    if not text:
        return 0
    
    try:
        # ניקוי ראשוני של רווחים ופסיקים, והפיכה לאותיות גדולות
        clean_text = text.strip().replace(",", "").upper()
        
        # חילוץ המספר והסיומת (K/M) בלבד באמצעות ביטוי רגולרי
        # המחפש מספר (כולל נקודה עשרונית) ואחריו אופציונלית K או M
        match = re.search(r'([\d.]+)\s*([KM]?)', clean_text)
        
        if not match:
            # אם לא נמצא מספר, ננסה לפחות לחלץ ספרות בלבד
            digits = re.sub(r'[^\d]', '', clean_text)
            return int(digits) if digits else 0

        number_part = match.group(1)
        suffix = match.group(2)
        
        val = float(number_part)
        
        if suffix == "M":
            return int(val * 1_000_000)
        if suffix == "K":
            return int(val * 1_000)
            
        return int(val)
        
    except (ValueError, TypeError, AttributeError):
        return 0

def get_profile_stats(driver: uc.Chrome, username: str = "") -> dict:
    stats = {"posts": 0, "followers": 0, "following": 0}
    try:
        # המתנה קצרה לטעינה - קריטי כדי שהמספרים יופיעו ב-DOM
        time.sleep(2)
        
        # מיפוי לפי הטקסט והמבנה המדויק ששלחת מה-Inspect
        xpath_map = {
            "posts": "//span[contains(., 'posts') or contains(., 'פוסטים')]",
            "followers": "//a[contains(@href, 'followers')] | //span[contains(., 'followers')]",
            "following": "//a[contains(@href, 'following')] | //span[contains(., 'following')]"
        }
        
        for key, xpath in xpath_map.items():
            try:
                el = driver.find_element(By.XPATH, xpath)
                
                # עדיפות ל-title כי שם נמצא המספר המדויק (למשל 949)
                val_text = el.get_attribute("title") 
                if not val_text:
                    try:
                        # חיפוש ב-span פנימי אם ה-title לא על האלמנט הראשי
                        val_text = el.find_element(By.XPATH, ".//span[@title]").get_attribute("title")
                    except:
                        val_text = el.text
                
                stats[key] = _parse_count(val_text)
            except:
                continue
        
        # הדפסת התוצאה ללוג כדי שנדע שזה עבד
        log.info(f"📊 Stats results for @{username}: {stats}")
        return stats

    except Exception as e:
        log.warning(f"⚠️ שגיאה בקריאת נתונים עבור {username}: {e}")
        return stats

# ═══════════════════════════════════════════════════════════════════════════════
#  FILTER & FOLLOW LOGIC
# ═══════════════════════════════════════════════════════════════════════════════


def passes_filter(followers: int, following: int) -> bool:
    """Return True when the target passes all audience-quality criteria."""
    if followers < FILTER_MIN_FOLLOWERS or followers == 0:
        return False
    if following > FILTER_MAX_FOLLOWING:
        return False
    rr = following / followers
    return FILTER_RR_MIN <= rr <= FILTER_RR_MAX


def is_already_following(driver: uc.Chrome, ai_enabled: bool = False) -> bool:
    el = smart_find(
        driver,
        goal="Following or Requested button",
        fallback_xpaths=FOLLOWING_CHECK_XPATHS,
        ai_enabled=ai_enabled,
        timeout=4,
    )
    return el is not None


def _check_rate_limit(driver: uc.Chrome) -> None:
    """Exit immediately if Instagram signals a rate-limit or action block."""
    rate_limit_phrases = [
        "try again later",
        "we limit how often",
        "action blocked",
        "something went wrong",
    ]
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        for phrase in rate_limit_phrases:
            if phrase in body_text:
                log.critical(
                    f"⛔  Instagram rate-limit detected: '{phrase}'. "
                    "Stopping to protect the account."
                )
                sys.exit(2)
    except Exception:
        pass


def follow_user(driver: uc.Chrome, ai_enabled: bool = False) -> bool:
    """
    Click the Follow button on the currently loaded profile page.
    Returns True on success, False otherwise.
    """
    try:
        btn = smart_find(
            driver,
            goal="Follow button on Instagram profile",
            fallback_xpaths=FOLLOW_XPATHS,
            ai_enabled=ai_enabled,
            timeout=8,
        )

        if not btn:
            log.info("Follow button not visible (private / already following).")
            return False

        if safe_click(driver, btn):
            human_sleep(1.5, 3.0)
            _check_rate_limit(driver)
            log.info("Follow action completed.")
            return True

        return False

    except SystemExit:
        raise  # propagate rate-limit exit
    except Exception as exc:
        log.warning(f"follow_user error: {exc}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  SUGGESTED USERS  — full 3-stage scraper
# ═══════════════════════════════════════════════════════════════════════════════


def get_suggested_users(
    driver: uc.Chrome, username: str, ai_enabled: bool = False
) -> list[str]:
    """
    Collect suggested usernames from a seed profile using three stages:
      1. Click the 'Discover people' / suggested icon on the profile header
      2. Click 'See all' to open the full modal
      3. Scrape all username hrefs from the modal dialog

    Falls back to smart_find (with optional AI) on Stage 1 if manual XPaths fail.
    Returns a list of username strings (may be empty on failure).
    """
    log.info(f"Fetching suggestions from seed: @{username}")
    driver.get(f"https://www.instagram.com/{username}/")
    human_sleep(3, 5)
    dismiss_dialogs(driver)

    # ── STAGE 1: click the "Discover people" icon ─────────────────────────────
    btn = None
    for xpath in _SUGGEST_ICON_XPATHS:
        try:
            btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            log.info(f"Stage 1: icon found via: {xpath}")
            break
        except TimeoutException:
            continue

    # If manual XPaths all failed, try smart_find with AI fallback
    if btn is None:
        btn = smart_find(
            driver,
            goal="Suggested / Discover people icon button on Instagram profile",
            fallback_xpaths=SUGGESTED_XPATHS,
            ai_enabled=ai_enabled,
            timeout=5,
        )

    if btn is None:
        log.warning("Stage 1 failed: could not locate the suggested icon.")
        try:
            with open("debug_failed_stage1.html", "w", encoding="utf-8") as fh:
                fh.write(driver.page_source)
            log.info("Page source saved to debug_failed_stage1.html")
        except Exception:
            pass
        return []

    try:
        btn.click()
    except Exception:
        driver.execute_script("arguments[0].click();", btn)
    human_sleep(2, 4)

    # ── STAGE 2: click "See all" ──────────────────────────────────────────────
    see_all_xpath = (
        "//a[contains(@href,'suggested_profiles') "
        "or contains(.,'See all') "
        "or contains(.,'הצג הכל')]"
    )
    try:
        see_all_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, see_all_xpath))
        )
        log.info("Stage 2: 'See all' found — opening modal.")
        driver.execute_script("arguments[0].click();", see_all_btn)
        human_sleep(3, 5)
    except TimeoutException:
        log.warning("Stage 2 failed: 'See all' link not found.")
        return []

    # ── STAGE 3: scrape usernames from the modal ──────────────────────────────
    usernames: list[str] = []
    _skip_keywords = {"explore", "reels", "p", "stories", "accounts", "about"}

    try:
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']"))
        )
        user_els = driver.find_elements(
            By.XPATH,
            "//div[@role='dialog']//a[@role='link' and starts-with(@href,'/')]",
        )
        for el in user_els:
            href = el.get_attribute("href") or ""
            uname = href.strip("/").split("/")[-1].split("?")[0]
            if (
                uname
                and uname not in usernames
                and uname != username
                and uname not in _skip_keywords
            ):
                usernames.append(uname)

        log.info(f"Stage 3: scraped {len(usernames)} suggested users.")
    except TimeoutException:
        log.error("Stage 3 failed: modal did not appear in time.")
    except Exception as exc:
        log.error(f"Stage 3 error: {exc}")

    return usernames


# ═══════════════════════════════════════════════════════════════════════════════
#  PROCESS SINGLE USER — Follow mode
# ═══════════════════════════════════════════════════════════════════════════════


def process_user_follow(
    driver: uc.Chrome,
    conn: sqlite3.Connection,
    username: str,
    ai_enabled: bool,
) -> bool:
    """
    Navigate to a profile, apply filters, and follow if criteria are met.
    Now supports following private accounts.
    """
    log.info(f"→ [FOLLOW] visiting @{username}")
    try:
        driver.get(f"https://www.instagram.com/{username}/")
        human_sleep(4, 7)
    except Exception as exc:
        log.warning(f"Navigation error for @{username}: {exc}")
        return False

    # Check for private status (for logging only, no longer skips)
    is_acc_private = False
    try:
        if is_private(driver):
            log.info(f"@{username} is private — proceeding with filters.")
            is_acc_private = True
    except Exception:
        pass

    # Gather stats
    try:
        stats = get_profile_stats(driver, username)
    except Exception as exc:
        log.warning(f"Stats extraction raised for @{username}: {exc}")
        db_upsert_user(conn, username, STATUS_SCANNED)
        return False

    followers = stats["followers"]
    following = stats["following"]
    ratio = following / followers if followers > 0 else 0.0

    log.info(
        f"@{username} — followers={followers:,}  following={following:,}  RR={ratio:.2f}"
    )

    # --- Filters ---
    if followers < FILTER_MIN_FOLLOWERS:
        log.info(f"Skip @{username}: too few followers ({followers}).")
        db_upsert_user(conn, username, STATUS_SCANNED)
        return False

    if followers > FILTER_MAX_FOLLOWING:
        log.info(f"Skip @{username}: too many followers ({followers}).")
        db_upsert_user(conn, username, STATUS_SCANNED)
        return False

    if following > FILTER_MAX_FOLLOWING:
        log.info(f"Skip @{username}: following count too high ({following}).")
        db_upsert_user(conn, username, STATUS_SCANNED)
        return False

    if not (FILTER_RR_MIN <= ratio <= FILTER_RR_MAX):
        log.info(
            f"Skip @{username}: ratio {ratio:.2f} outside "
            f"[{FILTER_RR_MIN}, {FILTER_RR_MAX}]."
        )
        db_upsert_user(conn, username, STATUS_SCANNED)
        return False

    log.info(f"✅ High-probability target: @{username}")
    dwell(username)

    # Locate follow button via smart_find
    try:
        btn = smart_find(
            driver,
            goal="Follow button on Instagram profile",
            fallback_xpaths=FOLLOW_XPATHS,
            ai_enabled=ai_enabled,
            timeout=8,
        )
    except Exception as exc:
        log.warning(f"smart_find raised for @{username}: {exc}")
        db_upsert_user(conn, username, STATUS_SCANNED)
        return False

    if btn is None:
        log.warning(f"Follow button not found for @{username}.")
        db_upsert_user(conn, username, STATUS_SCANNED)
        return False

    # Check button state (already following?)
    try:
        btn_text = btn.text.strip().lower()
        if any(w in btn_text for w in ("following", "requested", "עוקב", "נשלחה")):
            log.info(f"Already following @{username}.")
            db_upsert_user(conn, username, STATUS_FOLLOWED)
            return False
    except Exception:
        pass

    # Execute follow
    try:
        if safe_click(driver, btn):
            human_sleep(1.5, 3.0)
            _check_rate_limit(driver)
            
            status_msg = "Requested" if is_acc_private else "Followed"
            log.info(f"{status_msg} @{username}.")
            
            db_upsert_user(conn, username, STATUS_FOLLOWED)
            return True
    except SystemExit:
        raise
    except Exception as exc:
        log.warning(f"Click error for @{username}: {exc}")

    db_upsert_user(conn, username, STATUS_SCANNED)
    return False


# ═══════════════════════════════════════════════════════════════════════════════
#  PROCESS SINGLE USER — Scout mode
# ═══════════════════════════════════════════════════════════════════════════════


def process_user_scout(
    driver,
    conn: sqlite3.Connection,
    username: str,
) -> None:
    """Navigate to a profile and log stats to the scout report (no follow)."""
    log.info(f"→ [SCOUT] visiting @{username}")
    try:
        driver.get(f"https://www.instagram.com/{username}/")
        human_sleep(3, 5)
    except Exception as exc:
        log.warning(f"Navigation error for @{username}: {exc}")
        return
 
    try:
        stats = get_profile_stats(driver, username)
    except Exception as exc:
        log.warning(f"Stats error for @{username}: {exc}")
        stats = {"posts": 0, "followers": 0, "following": 0}
 
    followers = stats["followers"]
    following = stats["following"]
    rr = following / followers if followers > 0 else 0.0
    private = False
    last_post = "N/A"
 
    try:
        private = is_private(driver)
    except Exception:
        pass
 
    try:
        last_post = get_last_post_date(driver)
    except Exception:
        pass
 
    scout_report_write(username, followers, rr, private, last_post)
 
    note = "private account" if private else None
    db_upsert_user(conn, username, STATUS_SCANNED, notes=note)


# ═══════════════════════════════════════════════════════════════════════════════
#  MANUAL MODE
# ═══════════════════════════════════════════════════════════════════════════════


def run_manual_mode(
    driver: uc.Chrome, conn: sqlite3.Connection, txt_path: str
) -> None:
    """
    Read usernames from a TXT file, apply audience filters, and write
    passing profiles to MANUAL_OUTPUT_PATH for manual review / follow.
    """
    usernames = [
        u.strip()
        for u in Path(txt_path).read_text(encoding="utf-8").splitlines()
        if u.strip()
    ]
    log.info(f"Loaded {len(usernames)} usernames from {txt_path}")

    output = Path(MANUAL_OUTPUT_PATH)
    output.write_text("", encoding="utf-8")  # clear previous run
    passed = 0

    for username in usernames:
        if db_was_visited_recently(conn, username):
            log.info(f"@{username} visited recently — skipping.")
            continue

        log.info(f"→ [MANUAL] checking @{username}")
        try:
            driver.get(f"https://www.instagram.com/{username}/")
            human_sleep(2, 4)
            dismiss_dialogs(driver)
            human_scroll(driver)
        except Exception as exc:
            log.warning(f"Navigation error for @{username}: {exc}")
            continue

        try:
            if is_private(driver):
                log.info(f"@{username} is private — skipping.")
                db_upsert_user(conn, username, STATUS_SCANNED)
                human_sleep(*WAIT_BETWEEN_USERS)
                #continue
        except Exception:
            pass

        try:
            stats = get_profile_stats(driver, username)
        except Exception as exc:
            log.warning(f"Stats error for @{username}: {exc}")
            db_upsert_user(conn, username, STATUS_SCANNED)
            human_sleep(*WAIT_BETWEEN_USERS)
            continue

        followers = stats["followers"]
        following = stats["following"]

        if followers == 0:
            log.warning(f"@{username} — could not read stats.")
            db_upsert_user(conn, username, STATUS_SCANNED)
            human_sleep(*WAIT_BETWEEN_USERS)
            continue

        rr = round(following / followers, 2)
        log.info(
            f"Stats → followers={followers:,}  following={following:,}  RR={rr}"
        )

        if passes_filter(followers, following):
            log.info(f"✅  @{username} passed filter — saved to file.")
            with open(output, "a", encoding="utf-8") as fh:
                fh.write(f"https://www.instagram.com/{username}\n")
            passed += 1
        else:
            log.info(f"❌  @{username} did not pass filter.")

        db_upsert_user(conn, username, STATUS_SCANNED)
        human_sleep(*WAIT_BETWEEN_USERS)

    print(f"\n{'=' * 50}")
    print(f"✅  Manual filter complete.")
    print(f"   Passed : {passed} / {len(usernames)}")
    print(f"   Output : {MANUAL_OUTPUT_PATH}")
    print(f"{'=' * 50}\n")

# ══════════════════════════════════════════════════════════════════════════════
    #run_manual_mode
# ═══════════════════════════════════════════════════════════════════════════════
def _is_following_back(driver) -> bool:
    """
    Check whether the account whose profile is currently loaded is
    following us back.
 
    Strategy
    --------
    Look for the "Follows you" badge that Instagram renders beneath the
    username on their profile header.  Falls back to a page-text scan.
    Returns True only when positive confirmation is found; defaults to
    False (unfollow) on any ambiguity.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
 
    for xpath in FOLLOWERS_YOU_XPATHS:
        try:
            WebDriverWait(driver, 4).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            log.info("'Follows you' badge found — reciprocal follower confirmed.")
            return True
        except (TimeoutException, NoSuchElementException):
            continue
 
    # Final plain-text scan as a last resort
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        if "follows you" in body_text or "עוקב אחריך" in body_text:
            log.info("'Follows you' found in page text.")
            return True
    except Exception:
        pass
 
    return False
 
 
def _do_unfollow(driver) -> bool:
    """
    Execute the unfollow action on the currently loaded profile page.
 
    Flow
    ----
    1. Click the "Following" button — Instagram opens a confirmation dialog.
    2. Click "Unfollow" in that dialog.
    3. Verify the button has reverted to "Follow".
 
    Returns True on confirmed success, False otherwise.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException
 
    # Step 1 — click the "Following" (or "Requested") button to open dialog
    following_btn = smart_find(
        driver,
        goal="Following or Requested button",
        fallback_xpaths=FOLLOWING_CHECK_XPATHS,
        timeout=6,
    )
    if following_btn is None:
        log.warning("Following button not found — cannot unfollow.")
        return False
 
    if not safe_click(driver, following_btn):
        log.warning("safe_click on Following button failed.")
        return False
 
    human_sleep(1.0, 2.0)
    jitter_mouse(driver)
 
    # Step 2 — click "Unfollow" in the confirmation dialog
    unfollow_btn = smart_find(
        driver,
        goal="Unfollow confirmation button",
        fallback_xpaths=UNFOLLOW_CONFIRM_XPATHS,
        timeout=5,
    )
    if unfollow_btn is None:
        log.warning("Unfollow confirmation button not found.")
        return False
 
    if not safe_click(driver, unfollow_btn):
        log.warning("safe_click on Unfollow confirmation failed.")
        return False
 
    human_sleep(1.5, 3.0)
 
    # Step 3 — verify revert to "Follow" (success confirmation)
    try:
        follow_btn = smart_find(
            driver,
            goal="Follow button on Instagram profile",
            fallback_xpaths=FOLLOW_XPATHS,
            timeout=5,
        )
        if follow_btn is not None:
            log.info("Unfollow confirmed — Follow button is visible again.")
            return True
    except Exception:
        pass
 
    # If we can't re-find Follow, assume success unless we see "Following" again
    try:
        still_there = smart_find(
            driver,
            goal="Following or Requested button",
            fallback_xpaths=FOLLOWING_CHECK_XPATHS,
            timeout=3,
        )
        if still_there is None:
            log.info("Unfollow assumed successful (Following button gone).")
            return True
    except Exception:
        pass
 
    log.warning("Could not confirm unfollow outcome.")
    return False
 
 
def unfollow_logic(driver, conn: sqlite3.Connection) -> None:
    """
    Cleanup Mode — Unfollow Loop
    ════════════════════════════
    1. Query `users_status` for FOLLOWED users older than UNFOLLOW_AFTER_DAYS.
    2. For each candidate:
       a. Navigate to their profile.
       b. Check whether they follow us back (_is_following_back).
       c. If YES  → mark as FRIEND, skip unfollow.
       d. If NO   → execute _do_unfollow(), mark as UNFOLLOWED.
    3. Respect MAX_UNFOLLOWS_PER_RUN and _check_rate_limit on every action.
 
    Human-simulation functions (dwell, jitter_mouse, human_scroll, safe_click)
    are called at every appropriate point — identical to the follow loop.
    """
    import sys
 
    candidates = db_get_unfollow_candidates(conn)
 
    if not candidates:
        log.info(
            f"Cleanup: no FOLLOWED users older than {UNFOLLOW_AFTER_DAYS} days. "
            "Nothing to do."
        )
        return
 
    log.info(
        f"Cleanup: {len(candidates)} candidate(s) queued "
        f"(threshold = {UNFOLLOW_AFTER_DAYS} days)."
    )
 
    unfollowed_count = 0
 
    for row in candidates:
        username       = row["username"]
        followed_since = row["last_action_date"]
 
        # ── Daily / run-level cap ─────────────────────────────────────────────
        if unfollowed_count >= MAX_UNFOLLOWS_PER_RUN:
            log.info(
                f"Cleanup: reached MAX_UNFOLLOWS_PER_RUN ({MAX_UNFOLLOWS_PER_RUN}). "
                "Stopping."
            )
            break
 
        log.info(
            f"→ [CLEANUP] checking @{username}  "
            f"(followed since: {followed_since})"
        )
 
        # ── Navigate to profile ───────────────────────────────────────────────
        try:
            driver.get(f"https://www.instagram.com/{username}/")
            human_sleep(4, 7)
            dismiss_dialogs(driver)
        except Exception as exc:
            log.warning(f"Navigation error for @{username}: {exc}")
            human_sleep(*WAIT_BETWEEN_USERS)
            continue
 
        # ── Human simulation before any decision ─────────────────────────────
        human_scroll(driver)
        jitter_mouse(driver)
        dwell(username)           # realistic page-dwell before acting
 
        # ── Rate-limit guard ──────────────────────────────────────────────────
        try:
            _check_rate_limit(driver)
        except SystemExit:
            log.critical("Rate-limit detected during cleanup — stopping immediately.")
            raise
 
        # ── Reciprocal follow check ───────────────────────────────────────────
        try:
            follows_back = _is_following_back(driver)
        except Exception as exc:
            log.warning(f"Could not determine follow-back status for @{username}: {exc}")
            human_sleep(*WAIT_BETWEEN_USERS)
            continue
 
        if follows_back:
            log.info(f"@{username} follows back → marking as FRIEND.")
            db_upsert_user(conn, username, STATUS_FRIEND)
            human_sleep(*WAIT_BETWEEN_USERS)
            maybe_coffee_break()
            continue
 
        # ── Unfollow ──────────────────────────────────────────────────────────
        log.info(f"@{username} does NOT follow back → unfollowing.")
 
        try:
            success = _do_unfollow(driver)
        except SystemExit:
            raise
        except Exception as exc:
            log.error(f"Unfollow error for @{username}: {exc}")
            human_sleep(*WAIT_BETWEEN_USERS)
            continue
 
        if success:
            db_upsert_user(conn, username, STATUS_UNFOLLOWED)
            unfollowed_count += 1
            log.info(
                f"Unfollowed @{username}.  "
                f"Run tally: {unfollowed_count}/{MAX_UNFOLLOWS_PER_RUN}"
            )
            _check_rate_limit(driver)
        else:
            log.warning(
                f"Unfollow action for @{username} could not be confirmed — "
                "status unchanged."
            )
 
        human_sleep(*WAIT_BETWEEN_USERS)
        maybe_coffee_break()
 
    log.info(
        f"Cleanup run complete.  "
        f"Unfollowed: {unfollowed_count}  |  "
        f"Friends discovered: {len(candidates) - unfollowed_count - (len(candidates) - unfollowed_count)}"
    )

# ══════════════════════════════════════════════════════════════════════════════
#  BATCH  RUNNER
# ══════════════════════════════════════════════════════════════════════════════


def maybe_coffee_break() -> None:
    """הפסקות ארוכות - מבוטלות לחלוטין במצב פיתוח."""
    if DEBUG_MODE:
        return

    if random.random() < 0.08:  # 8% chance
        break_min = random.uniform(*COFFEE_BREAK_RANGE)
        log.info(f"☕ Taking a coffee break ({break_min:.1f} min)...")
        time.sleep(break_min * 60)


def check_bot_health(driver: uc.Chrome) -> bool:
    """
    ניווט לפרופיל האישי ובדיקת יחס עוקבים/נעקבים (RR).
    מחזיר False אם חרגנו מהרף (לעצור עוקבים), True אם הכל תקין.
    """
    log.info(f"Checking self-health for account...")
    try:
        # ניווט חכם דרך תפריט הצד כדי למנוע דף לבן
        log.info("Navigating via Sidebar click...")
        
        # מחפש את כפתור הפרופיל (עובד גם בעברית וגם באנגלית)
        sidebar_profile_xpath = "//a[.//span[text()='Profile' or text()='פרופיל'] or .//img[contains(@alt, 'profile')]]"
        
        try:
            profile_btn = WebDriverWait(driver, 12).until(
                EC.element_to_be_clickable((By.XPATH, sidebar_profile_xpath))
            )
            safe_click(driver, profile_btn)
            log.info("Successfully clicked profile button.")
        except Exception as e:
            log.warning(f"Could not click sidebar, trying direct URL: {e}")
            driver.get(f"https://www.instagram.com/{USERNAME}/")

        human_sleep(4, 6)
        
        # שליפת הנתונים מהדף
        stats = get_profile_stats(driver, USERNAME)
        
        if not stats:
            log.warning("Could not retrieve stats, skipping health check.")
            return True

        followers = stats.get("followers", 0)
        following = stats.get("following", 0)

        if followers == 0:
            log.info("No followers yet, continuing.")
            return True

        # חישוב ה-RR (Ratio)
        ratio = following / followers
        log.info(f"Self RR: {following}/{followers} = {ratio:.2f} (Limit: {RR_MAX_THRESHOLD})")

        if ratio > RR_MAX_THRESHOLD:
            log.warning("RR Threshold reached! Stopping follow actions for safety.")
            return False
        
        return True

    except Exception as exc:
        log.warning(f"Self-health check failed: {exc} — proceeding with caution.")
        return True


def run_batch(
    driver: uc.Chrome,
    conn: sqlite3.Connection,
    queue: deque,
    scout_mode: bool = False,
    ai_enabled: bool = False,
) -> str | None:
    """
    Process up to BATCH_SIZE users from the queue.

    Returns
    -------
    "__DAILY_LIMIT__"      — daily follow cap hit mid-batch
    "__RR_LIMIT_REACHED__" — own-account RR exceeded threshold
    last_followed          — username of the last successfully followed user
                             (used as the new seed for the next batch)
    None                   — no follows occurred this batch (scout or no matches)
    """
    batch: list[str] = []
    while queue and len(batch) < BATCH_SIZE:
        batch.append(queue.popleft())

    if not batch:
        log.warning("Queue empty — nothing to process.")
        return None

    mode_label = "SCOUT" if scout_mode else "FOLLOW"
    log.info(f"Batch start [{mode_label}]: {len(batch)} users.")
    last_followed: str | None = None

    for username in batch:
        # ── Pre-user checks (follow mode only) ────────────────────────────────
        if not scout_mode:
            # Probabilistic self-health check (~20 % of users)
            if random.random() < 0.20:
                if not check_bot_health(driver):
                    log.info("Self-correction: RR too high — ending batch.")
                    return "__RR_LIMIT_REACHED__"

            if db_follows_today(conn) >= MAX_FOLLOWS_PER_DAY:
                log.info(f"Daily limit reached ({MAX_FOLLOWS_PER_DAY}). Stopping.")
                return "__DAILY_LIMIT__"

        # ── Process user ───────────────────────────────────────────────────────
        try:
            if scout_mode:
                process_user_scout(driver, conn, username)
            else:
                followed = process_user_follow(driver, conn, username, ai_enabled)
                if followed:
                    last_followed = username
                    log.info(
                        f"Daily tally: {db_follows_today(conn)}/{MAX_FOLLOWS_PER_DAY}"
                    )
        except SystemExit:
            raise  # rate-limit exit must propagate
        except Exception as exc:
            log.error(f"Unhandled error processing @{username}: {exc}")

        maybe_coffee_break()
        human_sleep(*WAIT_BETWEEN_USERS)

    return last_followed  # None when scout_mode or no matches


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def run(seed: str = SEED_PROFILE) -> None:
    """
    Bot entry point.
    Shows the startup menu, waits for manual login, then dispatches to
    the selected mode:
      follow   → automatic follow loop
      scout    → stats-only scan loop
      manual   → TXT-file filter pass
      cleanup  → unfollow loop (new in v4.0)
    """
    if DEBUG_MODE:
        log.warning("⚠️  ATTENTION: DEBUG_MODE is ON. Bot will run fast!")

    config = startup_menu()
    mode = config["mode"]
    txt_path = config["txt_path"]
    scout_mode = (mode == "scout")

    log.info(f"Bot starting — mode: {mode.upper()}")

    conn   = db_connect()
    driver = build_driver()

    if scout_mode:
        scout_report_header()

    try:
        # ── Manual login wait ─────────────────────────────────────────────────
        manual_login_wait(driver)
        human_sleep(2, 4)

        # ── Cleanup (unfollow) mode ───────────────────────────────────────────
        if mode == "cleanup":
            log.info(
                f"Cleanup mode: will check FOLLOWED users older than "
                f"{UNFOLLOW_AFTER_DAYS} days."
            )
            unfollow_logic(driver, conn)
            return

        # ── Manual mode ───────────────────────────────────────────────────────
        if mode == "manual":
            run_manual_mode(driver, conn, txt_path)
            return

        # ── Auto / Scout loop ─────────────────────────────────────────────────
        current_seed = seed
        queue: deque = deque()

        while True:
            if not scout_mode and db_follows_today(conn) >= MAX_FOLLOWS_PER_DAY:
                log.info(f"Daily limit of {MAX_FOLLOWS_PER_DAY} reached. Exiting.")
                sys.exit(0)

            if len(queue) < BATCH_SIZE:
                fresh = get_suggested_users(driver, current_seed)
                added = 0
                for uname in fresh:
                    if uname not in queue and not db_was_visited_recently(conn, uname):
                        queue.append(uname)
                        added += 1

                if added > 0:
                    log.info(f"Added {added} fresh targets from @{current_seed}.")
                else:
                    log.warning(
                        f"All suggestions from @{current_seed} visited. "
                        "Rotating seed."
                    )
                    new_seed = db_get_random_followed(conn)
                    if new_seed and new_seed != current_seed:
                        current_seed = new_seed
                        log.info(f"🔄 New seed: @{current_seed}")
                    else:
                        log.warning("No alternative seed available — sleeping 2 min.")
                        time.sleep(120)
                    continue

            if not queue:
                log.warning("Queue empty after fetch — sleeping 2 min.")
                time.sleep(120)
                continue

            result = run_batch(driver, conn, queue, scout_mode)

            if result == "__DAILY_LIMIT__":
                log.info("Daily limit hit mid-batch. Exiting.")
                sys.exit(0)

            if result == "__RR_LIMIT_REACHED__":
                log.info("RR ratio too high. Exiting.")
                sys.exit(0)

            if result:
                log.info(f"Chain reaction → new seed: @{result}")
                current_seed = result
            else:
                log.info(f"No follows this batch — seed unchanged: @{current_seed}")

            sleep_sec = random.uniform(*WAIT_BETWEEN_BATCHES)
            
            if DEBUG_MODE:
                val = input(f"\n[DEBUG] Batch finished. Wait {sleep_sec/60:.1f} min? (y/Enter to skip): ").strip().lower()
                if val == 'y':
                    log.info(f"Debug: Waiting as requested ({sleep_sec/60:.1f} min)...")
                    time.sleep(sleep_sec)
                else:
                    log.info("Debug: Skipping batch wait.")
            else:
                log.info(f"Batch finished. Sleeping {sleep_sec/60:.1f} min...")
                time.sleep(sleep_sec)
    except KeyboardInterrupt:
        log.info("Stopped by user.")
    finally:
        conn.close()
        log.info("DB connection closed.")
        
        # לוגיקה לשמירת הדפדפן פתוח במצב מפתח
        if DEBUG_MODE:
            keep_open = input("\n[DEBUG] Keep browser open for next run? (y/n): ").strip().lower()
            if keep_open != 'y':
                driver.quit()
                log.info("Driver closed.")
            else:
                log.info("Keeping driver active. You can now restart the script without re-login.")
        else:
            driver.quit()
            log.info("Driver closed.")

# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    run()
