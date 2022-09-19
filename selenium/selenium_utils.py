
from selenium import webdriver # @UnresolvedImport
from selenium.webdriver.support.ui import WebDriverWait, Select # @UnresolvedImport
from selenium.webdriver.support import expected_conditions as EC # @UnresolvedImport
from selenium.webdriver.common.keys import Keys # @UnresolvedImport
from selenium.common.exceptions import WebDriverException, StaleElementReferenceException # @UnresolvedImport
from selenium.webdriver.common.by import By # @UnresolvedImport
from selenium.webdriver.chrome.service import Service

import os, sys, time
import shlex

driver = None
orig_url = None
delay = float(os.getenv("USECASE_REPLAY_DELAY", "0"))
test_id_key = "id"
add_explicit_display_tags = False
wait_timeout = 30

def run_with_usecase(url):
    setup(url)
    run_usecase()
    
def run_usecase():
    if os.path.isfile("usecase.py"):
        try:
            exec(compile(open("usecase.py").read(), "usecase.py", 'exec'))
        except Exception:
            capture_all_text("termination")
            close()
            raise

def get_downloads_dir():
    sandbox = os.getenv("TEXTTEST_SANDBOX")
    if sandbox:
        downloadsDir = os.path.join(sandbox, "downloads")
        if not os.path.isdir(downloadsDir):
            os.mkdir(downloadsDir)
        return downloadsDir

def setup(url):
    set_original_url(url)
    navigate(url)

def create_driver():    
    global driver
    options = webdriver.ChromeOptions()
    options.accept_insecure_certs = True
    screen_size = os.getenv("USECASE_SCREEN_SIZE")
    browser_lang = os.getenv("USECASE_UI_LANGUAGE")
    if browser_lang:
        options.add_argument("--lang=" + browser_lang)
    # if files get downloaded, make sure they get downloaded locally
    downloadsDir = get_downloads_dir()
    if downloadsDir:
        prefs = { "download.default_directory": downloadsDir,
                  "download.prompt_for_download": False,
                  "download.directory_upgrade": True,
                  "safebrowsing_for_trusted_sources_enabled": False,
                  "safebrowsing.enabled": False }
        options.add_experimental_option("prefs", prefs)
    if delay:
        if screen_size:
            options.add_argument("--window-size=" + screen_size)
            # possible alternative, but marked as experimental. Doesn't work the same as the browser interface anyway...
            #width, height = screen_size.split(",")
            #mobile_emulation = { "deviceMetrics": { "width": int(width), "height": int(height) } }
            #options.add_experimental_option("mobileEmulation", mobile_emulation)
        else:
            options.add_argument("--start-maximized")
    else:
        screen_size = screen_size or "1920,1080"
        options.add_argument("--window-size=" + screen_size)
        options.add_argument('headless')
    
    desired_capabilities = {}
    desired_capabilities['goog:loggingPrefs'] = {'browser':'ALL'}
    try:
        driver = webdriver.Chrome(desired_capabilities=desired_capabilities, options=options)
    except WebDriverException as e:
        # on Ubuntu, snap chromedriver has a non-default name it seems
        if os.name == "posix" and "executable needs to be in PATH" in str(e):
            service = Service("chromium.chromedriver")
            try:
                driver = webdriver.Chrome(desired_capabilities=desired_capabilities, options=options, service=service)
            except WebDriverException:
                raise e
        else:
            raise
    
def add_to_session_storage(key, value):
    driver.execute_script("sessionStorage.setItem('" + key + "', '" + value.replace("'", "\\'") + "');")

def set_original_url(url):
    create_driver()
    global orig_url
    orig_url = url
    
def navigate(url):
    if not url.startswith("http"):
        url = orig_url + url
    driver.get(url)
    
def back(ajax=False):
    tick()
    driver.back()
    if ajax:
        wait_for_ajax()
    capture_all_text("afterback_page")
    
def get_next_fn(fn):
    countText = fn[-13:-10]
    if countText == "2nd":
        return fn.replace(countText, "3rd")
    elif countText == "3rd":
        return fn.replace(countText, "4th")
    elif countText.endswith("th"):
        num = int(countText[0]) + 1
        return fn.replace(countText, str(num) + "th")
    else:
        return fn.replace("page", "2nd_page")
    
def test_id_xpath(test_id):
    return "//*[@" + test_id_key + "='" + test_id + "']"

def find_element_by_test_id(test_id):
    return driver.find_element(By.XPATH, test_id_xpath(test_id))

def enter_text(testid, text, replace=False, enter=False):
    textfield = find_element_by_test_id(testid)
    change_text_in_field(textfield, text, replace=replace, enter=enter)
    
def change_text_in_field(textfield, text, replace=False, tab=False, enter=False):
    if delay:
        time.sleep(delay)
    if replace:
        textfield.send_keys(Keys.CONTROL, "a")
        textfield.send_keys(Keys.DELETE)
    if text:
        textfield.send_keys(text)
    if tab:
        textfield.send_keys(Keys.TAB)
    if enter:
        textfield.send_keys(Keys.ENTER)
        
def replace_text_at_cursor(text, enter=False):
    activeElement = driver.switch_to.active_element
    change_text_in_field(activeElement, text, replace=True, enter=enter)

def enter_text_at_cursor(text, tab=False, enter=False):
    activeElement = driver.switch_to.active_element
    change_text_in_field(activeElement, text, tab=tab, enter=enter)

def fill_in_form(*texts):
    for i, text in enumerate(texts):
        lastText = i == len(texts) - 1
        enter_text_at_cursor(text, tab=not lastText, enter=lastText)


def shared_prefix_length(text1, text2):
    for i, letter in enumerate(text1):
        if i >= len(text2) or text2[i] != letter:
            return i

def edit_text_in_field(textfield, text, enter=False):
    if delay:
        time.sleep(delay)
    origText = textfield.get_attribute('value')
    sharedLen = shared_prefix_length(origText, text)
    for _ in range(len(origText) - sharedLen):
        textfield.send_keys(Keys.BACK_SPACE)
    textfield.send_keys(text[sharedLen:])
    if enter:
        textfield.send_keys(Keys.ENTER)

def find_shadow_dom_info(*selectorArgs):
    info = []
    if len(selectorArgs):
        for element in driver.find_elements(*selectorArgs):
            content = find_shadow_content(element.shadow_root)
            info.append((element, content))
        add_all_display_tags()
    else:
        for element in driver.find_elements(By.CSS_SELECTOR, "*"):
            if add_explicit_display_tags:
                make_display_explicit(element)
            try:
                shadow_root = element.shadow_root
                content = find_shadow_content(shadow_root)
                info.append((element, content))
            except WebDriverException:
                continue
    return info


def add_all_display_tags():
    if add_explicit_display_tags:
        for element in driver.find_elements(By.CSS_SELECTOR, "*"):
            make_display_explicit(element)

# get all 'root elements' whose parent is themselves.
# Normal search methods don't work in Shadow DOMs...
# Ignore styles for the shadow content, just cause clutter and can't easily be inserted
# into the main DOM html

def make_display_explicit(element):
    try:
        display = element.value_of_css_property("display")
        if display in ["flex", "inline-block"] or (display == "block" and element.tag_name != "div"):
            driver.execute_script("arguments[0].setAttribute('data-test-explicit-display',arguments[1])", element, display)
    except StaleElementReferenceException:
        # if something is stale, ignore it
        pass

def find_shadow_content(shadow_root):
    content = []
    for element in shadow_root.find_elements(By.CSS_SELECTOR, "*"):
        if element.tag_name != "style":
            parent = element.find_element(By.XPATH, ".//parent::*")
            if parent.id == element.id:
                content.append(element)
            if add_explicit_display_tags:
                make_display_explicit(element)
    return content


def search_in_dropdown(testid, text):
    tick()
    element = find_element_by_test_id(testid)
    element.send_keys(text)
    element.send_keys(Keys.DOWN)
    element.send_keys(Keys.ENTER)

        
def select_from_dropdown(testid, text):
    tick()
    select = Select(find_element_by_test_id(testid))
    select.select_by_visible_text(text)

def wait_until(condition, error=None, element=None):
    try:
        return WebDriverWait(element or driver, wait_timeout).until(condition)
    except Exception as e:
        print("Timed out!", error or element or driver, file=sys.stderr)
        raise
    
def wait_for_element(*selectorArgs, **kw):
    wait_until(EC.presence_of_element_located(selectorArgs), **kw)
    
def wait_for_visible(*selectorArgs, **kw):
    wait_until(EC.visibility_of_element_located(selectorArgs), **kw)
    
def wait_for_invisible(*selectorArgs, **kw):
    wait_until(EC.invisibility_of_element_located(selectorArgs), **kw)

def wait_for_clickable(*selectorArgs, **kw):
    wait_until(EC.element_to_be_clickable(selectorArgs), **kw)

def wait_for_ajax():
    wait_until(lambda d: d.execute_script("return jquery.active == 0"), error="Ajax operation did not complete")

def case_insensitive_text_to_be_present_in_element(locator, text_):
    # copied from Selenium. Can be useful not to worry about case, as this is often determined by styling
    def _predicate(driver):
        try:
            element_text = driver.find_element(*locator).text
            return text_.lower() in element_text.lower()
        except StaleElementReferenceException:
            return False

    return _predicate

def wait_for_case_insensitive_text(text, *selectorArgs, **kw):
    wait_until(case_insensitive_text_to_be_present_in_element(selectorArgs, text), **kw)

def wait_and_click(*selectorArgs, **kw):
    for _ in range(5):
        try:
            element = wait_until(EC.element_to_be_clickable(selectorArgs), error=repr(selectorArgs[-1]) + " not clickable", **kw)
            time.sleep(0.5)
            element.click()
            return
        except WebDriverException as e:
            if 'is not clickable at point' in str(e):
                time.sleep(0.1)
            else:
                raise

def wait_and_click_test_id(test_id):
    wait_and_click(By.XPATH, test_id_xpath(test_id))

def wait_for_download():
    downloadsDir = get_downloads_dir()
    if downloadsDir:
        for _ in range(wait_timeout * 10):
            files = [ fn for fn in os.listdir(downloadsDir) if not fn.endswith(".crdownload") ]
            if len(files) > 0:
                return
            else:
                time.sleep(0.1)
    raise WebDriverException("No download files available after waiting " + str(wait_timeout) + " seconds")
    
def tick(factor=1):
    if delay:
        time.sleep(delay * factor)
    
capture_numbered=False
page_number = 0
def capture_all_text(pagename="websource", element=None, shadow_dom_info=None):
    if delay:
        time.sleep(delay)
    fn = pagename + ".html"
    if capture_numbered:
        global page_number
        page_number += 1
        fn = str(page_number).zfill(3) + "_" + fn
    while os.path.isfile(fn):
        fn = get_next_fn(fn)
    driver.save_screenshot(fn.replace(".html", ".png"))
    with open(fn, mode="w") as f:
        if add_explicit_display_tags and not shadow_dom_info:
            add_all_display_tags()
        to_write = element.get_attribute("outerHTML") if element else driver.page_source
        if shadow_dom_info:
            for shadow_host, shadow_content in shadow_dom_info:
                contentHtml = ""
                for content in shadow_content:
                    contentHtml += content.get_attribute("outerHTML")
                to_write = to_write.replace(shadow_host.get_attribute("outerHTML"), contentHtml)
        f.write(to_write)
    
browser_console_file = sys.stderr
loglevels = { 'NOTSET':0 , 'DEBUG':10 ,'INFO': 20 , 'WARNING':30, 'ERROR':40, 'SEVERE':40, 'CRITICAL':50}
def close():
    global driver
    if driver != None:
        if delay:
            time.sleep(delay)
        for log_type in driver.log_types:
            for entry in driver.get_log(log_type):
                level = entry['level']
                levelNumber = loglevels.get(level, 99)
                log_file = sys.stderr if levelNumber > 25 else browser_console_file
                try:
                    message = entry['message']
                    parts = shlex.split(message)
                    if parts[0].endswith(".js"): # temporary file reference, add as postfix
                        message = " ".join(parts[2:])
                        file = parts[0].rsplit("/")[-1]
                        message += " (" + file + ":" + parts[1] + ")"
                    print(level + ":", message, file=log_file)
                except Exception:
                    print("FAILED to parse " + entry['message'] + '!', file=log_file)
        driver.quit()
        driver = None
    else:
        print("Couldn't close, driver == None")

