import json
import logging
import os
import platform
import random
import re
import sqlite3
import subprocess
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

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

INSTAGRAM_USERNAME = os.environ.get("INSTAGRAM_USERNAME", "")
SEED_PROFILE = os.environ.get("SEED_PROFILE", "example_user")

RR_MIN_THRESHOLD = 1.2
RR_MAX_THRESHOLD = 1.8

DEBUG_MODE = os.environ.get("DEBUG_MODE", "false").lower() in ("1", "true", "yes")
ENABLE_HEALTH_CHECKS = os.environ.get("ENABLE_HEALTH_CHECKS", "false").lower() in (
    "1",
    "true",
    "yes",
)

CHROME_PROFILE_PATH = os.environ.get(
    "CHROME_PROFILE_PATH", str(Path.home() / "IG_Bot_Chrome_Profile")
)
CHROME_BINARY = os.environ.get("CHROME_BINARY", "")
CHROME_VERSION_MAIN = os.environ.get("CHROME_VERSION_MAIN", "")

DB_PATH = os.environ.get("DB_PATH", "data/ig_bot.db")
SCOUT_REPORT_PATH = "scout_report.txt"
MANUAL_OUTPUT_PATH = "filtered_users.txt"
XPATH_CACHE_FILE = "xpath_cache.json"

UNFOLLOW_AFTER_DAYS = 7
MAX_UNFOLLOWS_PER_RUN = 25

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

BATCH_SIZE = 10
MAX_FOLLOWS_PER_DAY = 40
REVISIT_DAYS = 30

FILTER_MIN_FOLLOWERS = 300
FILTER_MAX_FOLLOWERS = 50_000
FILTER_MAX_FOLLOWING = 2000
FILTER_RR_MIN = 1.0
FILTER_RR_MAX = 5.0

DWELL_TIME_RANGE = (35, 55)
WAIT_BETWEEN_USERS = (5, 6)
WAIT_BETWEEN_BATCHES = (20 * 60, 40 * 60)

COFFEE_BREAK_CHANCE = 0.10
COFFEE_BREAK_RANGE = (20, 21)

FOLLOW_XPATHS = [
    "//button[contains(@class, '_aswp') and .//div[text()='Follow']]",
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
    "//*[normalize-space(text())='Follows you']",
    "//*[normalize-space(text())='עוקב אחריך']",
    "//*[contains(@class,'_aayn') and contains(.,'Follows you')]",
    "//span[contains(normalize-space(),'Follows you')]",
    "//*[contains(normalize-space(),'followed by')]",
]

UNFOLLOW_CONFIRM_XPATHS = [
    "//button[normalize-space(text())='Unfollow']",
    "//button[normalize-space()='Unfollow']",
    "//*[@role='button'][normalize-space()='Unfollow']",
    "//button[normalize-space(text())='הפסק לעקוב']",
    "//div[@role='dialog']//button[contains(normalize-space(),'Unfollow')]",
]

SUGGESTED_XPATHS = [
    "//div[@role='button' and .//*[name()='svg']]",
    "//*[preceding::button[normalize-space()='Follow'] or "
    "following::button[normalize-space()='Follow']][1]",
    "//header//*[@role='button'][.//*[name()='svg']][not(normalize-space()='Follow')][1]",
    "//button[normalize-space()='Follow']/following-sibling::*[@role='button'][1]",
    "//*[name()='svg'][@height='16' or @height='12']"
    "[contains(@viewBox,'24')]/ancestor::*[@role='button'][1]",
]

_SUGGEST_ICON_XPATHS = [
    "//div[@role='button'][.//svg[@aria-label='Similar accounts' or @aria-label='חשבונות דומים']]",
    "//div[@role='button'][.//svg[@aria-label='Discover people' or @aria-label='גילוי אנשים']]",
    "//header//section/div/div/div/div/div[3]/div[@role='button']",
    "//div[button[contains(.,'Message') or contains(.,'הודעה')]]/following-sibling::div//div[@role='button']",
]

STATUS_SCANNED = "SCANNED"
STATUS_FOLLOWED = "FOLLOWED"
STATUS_FRIEND = "FRIEND"
STATUS_UNFOLLOWED = "UNFOLLOWED"

_ai_client = None

_PRIVATE_PHRASES = [
    "this account is private",
    "follow to see their photos",
    "follow this account to see",
]


def startup_menu() -> dict:
    print("\n" + "=" * 55)
    print("        Instagram Bot — v4.0")
    print("=" * 55)
    print("\n1. Auto Follow")
    print("2. Scout only")
    print("3. Manual filter")
    print("4. Cleanup / Unfollow")

    while True:
        mode = input("\nSelect mode (1/2/3/4): ").strip()
        if mode in ("1", "2", "3", "4"):
            break
        print("Invalid choice. Enter 1, 2, 3, or 4.")

    txt_path = None
    if mode == "3":
        txt_path = input("\nPath to TXT file with usernames: ").strip()
        if not Path(txt_path).exists():
            print(f"File not found: {txt_path}")
            sys.exit(1)

    config = {
        "mode": {"1": "follow", "2": "scout", "3": "manual", "4": "cleanup"}[mode],
        "txt_path": txt_path,
    }

    print("\n" + "=" * 55)
    print(f"  Mode: {config['mode'].upper()}")
    if txt_path:
        print(f"  TXT : {txt_path}")
    print("=" * 55 + "\n")
    time.sleep(1)
    return config


def _get_ai_client():
    global _ai_client
    if _ai_client is None:
        if not ANTHROPIC_API_KEY:
            log.warning("ANTHROPIC_API_KEY is empty — AI XPath recovery disabled.")
            return None
        try:
            import anthropic

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
    client = _get_ai_client()
    if not client:
        return None

    log.info(f"AI XPath lookup for: '{goal}'")
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
            log.info(f"AI found XPath: {result['xpath']}")
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
    for xpath in fallback_xpaths:
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            return el
        except TimeoutException:
            continue

    cache = _load_xpath_cache()
    if goal in cache:
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, cache[goal]))
            )
            log.info("Found element via XPath cache")
            return el
        except TimeoutException:
            log.warning("Cached XPath failed — removing and retrying")
            del cache[goal]
            _save_xpath_cache(cache)

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


def db_connect() -> sqlite3.Connection:
    db_file = Path(DB_PATH)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    legacy = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='visited'"
    ).fetchone()

    if legacy:
        try:
            conn.execute("ALTER TABLE visited RENAME TO _visited_legacy")
            conn.commit()
            log.info("Legacy `visited` table preserved as `_visited_legacy`.")
        except Exception:
            pass

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


def db_upsert_user(
    conn: sqlite3.Connection, username: str, status: str, notes: str | None = None
) -> None:
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
    row = conn.execute(
        "SELECT 1 FROM users_status WHERE username = ? "
        "AND last_action_date > datetime('now', ?)",
        (username, f"-{REVISIT_DAYS} days"),
    ).fetchone()
    return row is not None


def db_follows_today(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM users_status "
        "WHERE status = ? AND date(last_action_date) = date('now')",
        (STATUS_FOLLOWED,),
    ).fetchone()
    return row[0] if row else 0


def db_get_random_followed(conn: sqlite3.Connection) -> str:
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
    rows = conn.execute(
        "SELECT username, last_action_date, notes FROM users_status "
        "WHERE status = ? "
        "AND last_action_date <= datetime('now', ?) "
        "ORDER BY last_action_date ASC LIMIT ?",
        (STATUS_FOLLOWED, f"-{UNFOLLOW_AFTER_DAYS} days", MAX_UNFOLLOWS_PER_RUN),
    ).fetchall()
    return rows


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


def _default_chrome_binary() -> str | None:
    if CHROME_BINARY:
        return CHROME_BINARY
    system = platform.system()
    if system == "Windows":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", ""))
            / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Google/Chrome/Application/chrome.exe",
        ]
    elif system == "Darwin":
        candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
    else:
        candidates = [
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/google-chrome-stable"),
            Path("/usr/bin/chromium-browser"),
        ]
    for path in candidates:
        if path and path.exists():
            return str(path)
    return None


def _detect_chrome_version_main(chrome_binary: str | None) -> int | None:
    if not chrome_binary:
        return None
    try:
        result = subprocess.run(
            [chrome_binary, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        output = f"{result.stdout} {result.stderr}"
        match = re.search(r"(?:Chrome|Chromium)[/\s](\d+)\.", output, re.I)
        if match:
            return int(match.group(1))
    except Exception as exc:
        log.debug(f"Chrome version detection failed: {exc}")
    return None


def _resolve_chrome_version_main(chrome_binary: str | None) -> int | None:
    if CHROME_VERSION_MAIN:
        return int(CHROME_VERSION_MAIN)
    return _detect_chrome_version_main(chrome_binary)


def build_driver() -> uc.Chrome:
    options = uc.ChromeOptions()

    chrome_binary = _default_chrome_binary()
    if chrome_binary:
        options.binary_location = chrome_binary

    options.add_argument(f"--user-data-dir={CHROME_PROFILE_PATH}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-service-autorun")
    options.add_argument("--password-store=basic")
    options.add_argument("--window-size=1366,768")

    version_main = _resolve_chrome_version_main(chrome_binary)
    driver_kwargs: dict = {"options": options, "headless": False}
    if version_main is not None:
        driver_kwargs["version_main"] = version_main

    try:
        driver = uc.Chrome(**driver_kwargs)
        log.info(
            f"Driver started with profile: {CHROME_PROFILE_PATH} "
            f"(Chrome major={version_main})"
        )
        return driver
    except Exception as e:
        log.error(f"Failed to start Chrome: {e}")
        sys.exit(1)


def human_sleep(min_s: float, max_s: float) -> None:
    if DEBUG_MODE:
        time.sleep(0.5)
        return
    duration = random.uniform(min_s, max_s)
    log.info(f"Sleeping {duration:.1f}s...")
    time.sleep(duration)


def maybe_coffee_break() -> None:
    if DEBUG_MODE:
        return
    if random.random() < COFFEE_BREAK_CHANCE:
        break_min = random.uniform(*COFFEE_BREAK_RANGE)
        log.info(f"Coffee break ({break_min:.1f} min)...")
        time.sleep(break_min * 60)


def dwell(username: str) -> None:
    if DEBUG_MODE:
        human_sleep(0.5, 0.5)
        return
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
            log.warning("2FA / challenge detected.")
            log.warning("Complete verification in the browser, then press ENTER.")
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
    driver.get("https://www.instagram.com/accounts/login/")
    log.info("Manual login required in the browser window.")
    input("\nPress ENTER after you see the Instagram feed: ")
    handle_2fa_or_challenge(driver)
    log.info("Login confirmed. Starting automation...")
    dismiss_dialogs(driver)


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


def _parse_count(text: str) -> int:
    if not text:
        return 0

    try:
        clean_text = text.strip().replace(",", "").upper()
        match = re.search(r"([\d.]+)\s*([KM]?)", clean_text)

        if not match:
            digits = re.sub(r"[^\d]", "", clean_text)
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
        if not DEBUG_MODE:
            time.sleep(2)

        xpath_map = {
            "posts": "//span[contains(., 'posts') or contains(., 'פוסטים')]",
            "followers": "//a[contains(@href, 'followers')] | //span[contains(., 'followers')]",
            "following": "//a[contains(@href, 'following')] | //span[contains(., 'following')]",
        }

        for key, xpath in xpath_map.items():
            try:
                el = driver.find_element(By.XPATH, xpath)
                val_text = el.get_attribute("title")
                if not val_text:
                    try:
                        val_text = el.find_element(
                            By.XPATH, ".//span[@title]"
                        ).get_attribute("title")
                    except NoSuchElementException:
                        val_text = el.text
                stats[key] = _parse_count(val_text)
            except NoSuchElementException:
                continue

        log.info(f"Stats for @{username}: {stats}")
        return stats
    except Exception as e:
        log.warning(f"Stats error for {username}: {e}")
        return stats


def passes_filter(followers: int, following: int) -> bool:
    if followers < FILTER_MIN_FOLLOWERS or followers == 0:
        return False
    if followers > FILTER_MAX_FOLLOWERS:
        return False
    if following > FILTER_MAX_FOLLOWING:
        return False
    rr = following / followers
    return FILTER_RR_MIN <= rr <= FILTER_RR_MAX


def _check_rate_limit(driver: uc.Chrome) -> None:
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
                    f"Instagram rate-limit detected: '{phrase}'. Stopping."
                )
                sys.exit(2)
    except Exception:
        pass


def get_suggested_users(
    driver: uc.Chrome, username: str, ai_enabled: bool = False
) -> list[str]:
    log.info(f"Fetching suggestions from seed: @{username}")
    driver.get(f"https://www.instagram.com/{username}/")
    human_sleep(3, 5)
    dismiss_dialogs(driver)

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

    see_all_xpath = (
        "//a[contains(@href,'suggested_profiles') "
        "or contains(.,'See all') "
        "or contains(.,'הצג הכל')]"
    )
    try:
        see_all_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, see_all_xpath))
        )
        log.info("Stage 2: 'See all' found.")
        driver.execute_script("arguments[0].click();", see_all_btn)
        human_sleep(3, 5)
    except TimeoutException:
        log.warning("Stage 2 failed: 'See all' link not found.")
        return []

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


def process_user_follow(
    driver: uc.Chrome,
    conn: sqlite3.Connection,
    username: str,
    ai_enabled: bool,
) -> bool:
    log.info(f"[FOLLOW] visiting @{username}")
    try:
        driver.get(f"https://www.instagram.com/{username}/")
        human_sleep(4, 7)
    except Exception as exc:
        log.warning(f"Navigation error for @{username}: {exc}")
        return False

    is_acc_private = False
    try:
        if is_private(driver):
            log.info(f"@{username} is private — proceeding with filters.")
            is_acc_private = True
    except Exception:
        pass

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

    if not passes_filter(followers, following):
        log.info(f"Skip @{username}: did not pass filters.")
        db_upsert_user(conn, username, STATUS_SCANNED)
        return False

    log.info(f"Target accepted: @{username}")
    dwell(username)

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

    try:
        btn_text = btn.text.strip().lower()
        if any(w in btn_text for w in ("following", "requested", "עוקב", "נשלחה")):
            log.info(f"Already following @{username}.")
            db_upsert_user(conn, username, STATUS_FOLLOWED)
            return False
    except Exception:
        pass

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


def process_user_scout(
    driver,
    conn: sqlite3.Connection,
    username: str,
) -> None:
    log.info(f"[SCOUT] visiting @{username}")
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


def run_manual_mode(
    driver: uc.Chrome, conn: sqlite3.Connection, txt_path: str
) -> None:
    usernames = [
        u.strip()
        for u in Path(txt_path).read_text(encoding="utf-8").splitlines()
        if u.strip()
    ]
    log.info(f"Loaded {len(usernames)} usernames from {txt_path}")

    output = Path(MANUAL_OUTPUT_PATH)
    output.write_text("", encoding="utf-8")
    passed = 0

    for username in usernames:
        if db_was_visited_recently(conn, username):
            log.info(f"@{username} visited recently — skipping.")
            continue

        log.info(f"[MANUAL] checking @{username}")
        try:
            driver.get(f"https://www.instagram.com/{username}/")
            human_sleep(2, 4)
            dismiss_dialogs(driver)
            human_scroll(driver)
        except Exception as exc:
            log.warning(f"Navigation error for @{username}: {exc}")
            continue

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
            log.info(f"@{username} passed filter — saved to file.")
            with open(output, "a", encoding="utf-8") as fh:
                fh.write(f"https://www.instagram.com/{username}\n")
            passed += 1
        else:
            log.info(f"@{username} did not pass filter.")

        db_upsert_user(conn, username, STATUS_SCANNED)
        human_sleep(*WAIT_BETWEEN_USERS)

    print(f"\n{'=' * 50}")
    print("Manual filter complete.")
    print(f"Passed : {passed} / {len(usernames)}")
    print(f"Output : {MANUAL_OUTPUT_PATH}")
    print(f"{'=' * 50}\n")


def _is_following_back(driver) -> bool:
    for xpath in FOLLOWERS_YOU_XPATHS:
        try:
            WebDriverWait(driver, 4).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            log.info("'Follows you' badge found.")
            return True
        except (TimeoutException, NoSuchElementException):
            continue

    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        if "follows you" in body_text or "עוקב אחריך" in body_text:
            log.info("'Follows you' found in page text.")
            return True
    except Exception:
        pass

    return False


def _do_unfollow(driver) -> bool:
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

    try:
        follow_btn = smart_find(
            driver,
            goal="Follow button on Instagram profile",
            fallback_xpaths=FOLLOW_XPATHS,
            timeout=5,
        )
        if follow_btn is not None:
            log.info("Unfollow confirmed — Follow button visible again.")
            return True
    except Exception:
        pass

    try:
        still_there = smart_find(
            driver,
            goal="Following or Requested button",
            fallback_xpaths=FOLLOWING_CHECK_XPATHS,
            timeout=3,
        )
        if still_there is None:
            log.info("Unfollow assumed successful.")
            return True
    except Exception:
        pass

    log.warning("Could not confirm unfollow outcome.")
    return False


def unfollow_logic(driver, conn: sqlite3.Connection) -> None:
    candidates = db_get_unfollow_candidates(conn)

    if not candidates:
        log.info(
            f"Cleanup: no FOLLOWED users older than {UNFOLLOW_AFTER_DAYS} days."
        )
        return

    log.info(
        f"Cleanup: {len(candidates)} candidate(s) "
        f"(threshold = {UNFOLLOW_AFTER_DAYS} days)."
    )

    unfollowed_count = 0
    friends_count = 0

    for row in candidates:
        username = row["username"]
        followed_since = row["last_action_date"]

        if unfollowed_count >= MAX_UNFOLLOWS_PER_RUN:
            log.info(
                f"Cleanup: reached MAX_UNFOLLOWS_PER_RUN ({MAX_UNFOLLOWS_PER_RUN})."
            )
            break

        log.info(
            f"[CLEANUP] checking @{username} (followed since: {followed_since})"
        )

        try:
            driver.get(f"https://www.instagram.com/{username}/")
            human_sleep(4, 7)
            dismiss_dialogs(driver)
        except Exception as exc:
            log.warning(f"Navigation error for @{username}: {exc}")
            human_sleep(*WAIT_BETWEEN_USERS)
            continue

        human_scroll(driver)
        jitter_mouse(driver)
        dwell(username)

        try:
            _check_rate_limit(driver)
        except SystemExit:
            log.critical("Rate-limit detected during cleanup — stopping.")
            raise

        try:
            follows_back = _is_following_back(driver)
        except Exception as exc:
            log.warning(f"Could not determine follow-back status for @{username}: {exc}")
            human_sleep(*WAIT_BETWEEN_USERS)
            continue

        if follows_back:
            log.info(f"@{username} follows back → marking as FRIEND.")
            db_upsert_user(conn, username, STATUS_FRIEND)
            friends_count += 1
            human_sleep(*WAIT_BETWEEN_USERS)
            maybe_coffee_break()
            continue

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
                f"Unfollowed @{username}. "
                f"Run tally: {unfollowed_count}/{MAX_UNFOLLOWS_PER_RUN}"
            )
            _check_rate_limit(driver)
        else:
            log.warning(f"Unfollow for @{username} could not be confirmed.")

        human_sleep(*WAIT_BETWEEN_USERS)
        maybe_coffee_break()

    log.info(
        f"Cleanup complete. Unfollowed: {unfollowed_count} | Friends: {friends_count}"
    )


def check_bot_health(driver: uc.Chrome) -> bool:
    if not ENABLE_HEALTH_CHECKS:
        log.info("Self-health check skipped (disabled).")
        return True

    profile = INSTAGRAM_USERNAME or SEED_PROFILE
    log.info("Checking self-health...")
    try:
        sidebar_profile_xpath = (
            "//a[.//span[text()='Profile' or text()='פרופיל'] "
            "or .//img[contains(@alt, 'profile')]]"
        )

        try:
            profile_btn = WebDriverWait(driver, 12).until(
                EC.element_to_be_clickable((By.XPATH, sidebar_profile_xpath))
            )
            safe_click(driver, profile_btn)
            log.info("Clicked profile button.")
        except Exception as e:
            log.warning(f"Sidebar click failed, using direct URL: {e}")
            driver.get(f"https://www.instagram.com/{profile}/")

        human_sleep(4, 6)
        stats = get_profile_stats(driver, profile)

        followers = stats.get("followers", 0)
        following = stats.get("following", 0)

        if followers == 0:
            log.info("No followers yet, continuing.")
            return True

        ratio = following / followers
        log.info(
            f"Self RR: {following}/{followers} = {ratio:.2f} "
            f"(limit: {RR_MAX_THRESHOLD})"
        )

        if ratio > RR_MAX_THRESHOLD:
            log.warning("RR threshold reached. Stopping follow actions.")
            return False

        return True
    except Exception as exc:
        log.warning(f"Self-health check failed: {exc}")
        return True


def run_batch(
    driver: uc.Chrome,
    conn: sqlite3.Connection,
    queue: deque,
    scout_mode: bool = False,
    ai_enabled: bool = False,
) -> str | None:
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
        if not scout_mode:
            if ENABLE_HEALTH_CHECKS and random.random() < 0.20:
                if not check_bot_health(driver):
                    log.info("Self-correction: RR too high — ending batch.")
                    return "__RR_LIMIT_REACHED__"

            if db_follows_today(conn) >= MAX_FOLLOWS_PER_DAY:
                log.info(f"Daily limit reached ({MAX_FOLLOWS_PER_DAY}). Stopping.")
                return "__DAILY_LIMIT__"

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
            raise
        except Exception as exc:
            log.error(f"Unhandled error processing @{username}: {exc}")

        maybe_coffee_break()
        human_sleep(*WAIT_BETWEEN_USERS)

    return last_followed


def run(seed: str = SEED_PROFILE) -> None:
    if DEBUG_MODE:
        log.warning("DEBUG_MODE is ON. Bot will run fast.")

    config = startup_menu()
    mode = config["mode"]
    txt_path = config["txt_path"]
    scout_mode = mode == "scout"
    ai_enabled = bool(ANTHROPIC_API_KEY)

    log.info(f"Bot starting — mode: {mode.upper()}")

    conn = db_connect()
    driver = build_driver()

    if scout_mode:
        scout_report_header()

    try:
        manual_login_wait(driver)
        human_sleep(2, 4)

        if mode == "cleanup":
            log.info(
                f"Cleanup mode: checking FOLLOWED users older than "
                f"{UNFOLLOW_AFTER_DAYS} days."
            )
            unfollow_logic(driver, conn)
            return

        if mode == "manual":
            run_manual_mode(driver, conn, txt_path)
            return

        current_seed = seed
        queue: deque = deque()

        while True:
            if not scout_mode and db_follows_today(conn) >= MAX_FOLLOWS_PER_DAY:
                log.info(f"Daily limit of {MAX_FOLLOWS_PER_DAY} reached. Exiting.")
                sys.exit(0)

            if len(queue) < BATCH_SIZE:
                fresh = get_suggested_users(driver, current_seed, ai_enabled)
                added = 0
                for uname in fresh:
                    if uname not in queue and not db_was_visited_recently(conn, uname):
                        queue.append(uname)
                        added += 1

                if added > 0:
                    log.info(f"Added {added} fresh targets from @{current_seed}.")
                else:
                    log.warning(
                        f"All suggestions from @{current_seed} visited. Rotating seed."
                    )
                    new_seed = db_get_random_followed(conn)
                    if new_seed and new_seed != current_seed:
                        current_seed = new_seed
                        log.info(f"New seed: @{current_seed}")
                    else:
                        log.warning("No alternative seed available — sleeping 2 min.")
                        time.sleep(120)
                    continue

            if not queue:
                log.warning("Queue empty after fetch — sleeping 2 min.")
                time.sleep(120)
                continue

            result = run_batch(driver, conn, queue, scout_mode, ai_enabled)

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
                val = input(
                    f"\n[DEBUG] Batch finished. Wait {sleep_sec / 60:.1f} min? "
                    f"(y/Enter to skip): "
                ).strip().lower()
                if val == "y":
                    log.info(f"Debug: waiting {sleep_sec / 60:.1f} min...")
                    time.sleep(sleep_sec)
                else:
                    log.info("Debug: skipping batch wait.")
            else:
                log.info(f"Batch finished. Sleeping {sleep_sec / 60:.1f} min...")
                time.sleep(sleep_sec)
    except KeyboardInterrupt:
        log.info("Stopped by user.")
    finally:
        conn.close()
        log.info("DB connection closed.")

        if DEBUG_MODE:
            keep_open = input(
                "\n[DEBUG] Keep browser open for next run? (y/n): "
            ).strip().lower()
            if keep_open != "y":
                driver.quit()
                log.info("Driver closed.")
            else:
                log.info("Keeping browser open for next run.")
        else:
            driver.quit()
            log.info("Driver closed.")


if __name__ == "__main__":
    run()
