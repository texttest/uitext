
from selenium import webdriver # @UnresolvedImport
from selenium.webdriver.support.ui import WebDriverWait, Select # @UnresolvedImport
from selenium.webdriver.support import expected_conditions as EC # @UnresolvedImport
from selenium.webdriver.common.keys import Keys # @UnresolvedImport
from selenium.common.exceptions import WebDriverException, StaleElementReferenceException,\
    NoSuchElementException # @UnresolvedImport
from selenium.webdriver.common.by import By as SeleniumBy # @UnresolvedImport
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains

import os, sys, time
import shlex
from datetime import datetime

driver = None
orig_url = None
delay = float(os.getenv("USECASE_REPLAY_DELAY", "0"))

test_id_key = "data-test-id"
allow_insecure_content = False
class By(SeleniumBy):
    TEST_ID = "test id"

add_explicit_display_tags = False
wait_timeout = 30

def run_with_usecase(url, **kw):
    setup(url, **kw)
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

def setup(url, **kw):
    set_original_url(url, **kw)
    navigate(url)

def create_driver():    
    # chrome is default - we can fetch the logs which leads to better testing
    create_chrome_driver()
    
def add_chromium_default_download(options, downloadsDir):
    prefs = { "download.default_directory": downloadsDir,
              "download.prompt_for_download": False,
              "download.directory_upgrade": True,
              "safebrowsing_for_trusted_sources_enabled": False,
              "safebrowsing.enabled": False }
    options.add_experimental_option("prefs", prefs)

def add_chromium_screen_options(options, delay):
    screen_size = os.getenv("USECASE_SCREEN_SIZE")
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
        options.add_argument('--window-position=-2400,-2400')
        options.add_argument('--headless=new')

def create_driver_object_and_retry(clsName, options):
    global driver
    attempts = 5
    for attempt in range(attempts):
        try:
            driver = clsName(options=options)
            return
        except (OSError, WebDriverException):
            # This automatically downloads the relevant driver in a given place
            # So if two tests do this simultaneously they might clash
            # wait a bit and try again.
            if attempt == attempts - 1:
                raise
            else:
                time.sleep(1)
        
def create_chrome_driver():    
    options = webdriver.ChromeOptions()
    options.accept_insecure_certs = True
    options.add_argument("--disable-search-engine-choice-screen")
    if allow_insecure_content:
        options.add_argument("--allow-running-insecure-content")
    browser_lang = os.getenv("USECASE_UI_LANGUAGE")
    if browser_lang:
        options.add_argument("--lang=" + browser_lang)
    # if files get downloaded, make sure they get downloaded locally
    downloadsDir = get_downloads_dir()
    if downloadsDir:
        add_chromium_default_download(options, downloadsDir)
    add_chromium_screen_options(options, delay)
    
    options.set_capability('goog:loggingPrefs', {'browser':'ALL'})
    create_driver_object_and_retry(webdriver.Chrome, options)
    enable_clipboard_permissions()

        
def create_firefox_driver():
    options = webdriver.FirefoxOptions()
    if allow_insecure_content:
        options.set_preference("security.mixed_content.block_active_content", False)
        options.set_preference("security.mixed_content.block_display_content", True)
    downloadsDir = get_downloads_dir()
    if downloadsDir:
        options.set_preference("browser.download.folderList", 2)
        options.set_preference("browser.download.manager.showWhenStarting", False)
        options.set_preference("browser.download.dir", downloadsDir)
        options.set_preference("browser.helperApps.neverAsk.saveToDisk", "application/x-gzip")
    if not delay:
        screen_size = os.getenv("USECASE_SCREEN_SIZE", "1920,1080")
        width, height = screen_size.split(",")
        options.headless = True
        options.add_argument("--width=" + width)
        options.add_argument("--height=" + height)
    create_driver_object_and_retry(webdriver.Firefox, options)

def enable_clipboard_permissions():
    driver.execute_cdp_cmd(
        cmd="Browser.grantPermissions",
        cmd_args={
            'permissions': ['clipboardReadWrite']
        }
    )
        
def create_edge_driver():
    options = webdriver.EdgeOptions()
    options.use_chromium = True
    options.accept_insecure_certs = True
    if allow_insecure_content:
        options.add_argument("--allow-running-insecure-content")
    
    downloadsDir = get_downloads_dir()
    if downloadsDir:
        add_chromium_default_download(options, downloadsDir)
    add_chromium_screen_options(options, delay)
    options.set_capability('ms:loggingPrefs', {'browser':'ALL'})
    create_driver_object_and_retry(webdriver.Edge, options)

def get_from_session_storage(key):
    return driver.execute_script("return sessionStorage.getItem('" + key + "');")
    
def add_to_session_storage(key, value):
    driver.execute_script("sessionStorage.setItem('" + key + "', '" + value.replace("'", "\\'") + "');")

def add_capturemock_cookie(value):
    if orig_url and not driver.current_url.startswith(orig_url):
        navigate("/favicon.ico") # somewhere so we can set cookies
  
    driver.add_cookie({"name": "capturemock_proxy_target", "value" : value })

def set_original_url(url, browser="chrome"):
    if browser == "firefox":
        create_firefox_driver()
    elif browser == "edge":
        create_edge_driver()
    else:
        create_chrome_driver()
    global orig_url
    orig_url = url
    # Any warning logs that get written before we navigate to the page under test should by definition not affect the test!
    fetch_logs(serious_only=True, serious_level='ERROR')

    
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

def make_selector(by, value):
    if by == By.TEST_ID:
        return By.XPATH, test_id_xpath(value)
    else:
        return by, value  

def find_element(by, value):
    return driver.find_element(*make_selector(by, value))

def find_elements(by, value):
    return driver.find_elements(*make_selector(by, value))

def enter_text(by, value, text, replace=False, enter=False):
    textfield = find_element(by, value)
    change_text_in_field(textfield, text, replace=replace, enter=enter)

def clear_text_field(textfield):
    textfield.send_keys(Keys.CONTROL, "a")
    textfield.send_keys(Keys.DELETE)
    # Seems to fail sometimes on Edge/Linux. Fix it up.
    if driver.capabilities['browserName'] == "msedge":
        for i in range(5):
            if len(textfield.get_attribute("value")) > 0:
                textfield.send_keys(Keys.CONTROL, "a")
                textfield.send_keys(Keys.DELETE)
                if i == 4:
                    raise WebDriverException("Failed to clear text field after 5 attempts!")
                else:
                    time.sleep(0.5)
            else:
                return
    
def change_text_in_field(textfield, text, replace=False, tab=False, enter=False):
    if delay:
        time.sleep(delay)
    if replace:
        clear_text_field(textfield)
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
        for element in driver.find_elements(*make_selector(*selectorArgs)):
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
        for element in driver.find_elements(By.CSS_SELECTOR, add_explicit_display_tags):
            make_display_explicit(element)

# get all 'root elements' whose parent is themselves.
# Normal search methods don't work in Shadow DOMs...
# Ignore styles for the shadow content, just cause clutter and can't easily be inserted
# into the main DOM html

def make_display_explicit(element):
    try:
        display = element.value_of_css_property("display")
        if (display in ["flex", "inline-block"] and element.tag_name != "span") or \
            (display == "block" and element.tag_name != "div") or \
            (display == "none" and element.tag_name not in [ "script", "style", "head", "meta", "title", "base", "link" ]):
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
    return content

def find_text_in_dropdown(by, value, text):
    arrowKey = Keys.DOWN
    for _ in range(20):
        activeElement = driver.switch_to.active_element
        try:
            elem = find_element(by, value)
        except NoSuchElementException:
            # might not be anything selected initially, press down and wait
            activeElement.send_keys(arrowKey)
            elem = wait_for_element(by, value)
            
        if elem.text == text:
            return activeElement.send_keys(Keys.ENTER)
        else:
            activeElement.send_keys(arrowKey)
    raise WebDriverException("Failed to find the text '" + text + "' in the dropdown!")


def search_in_dropdown(by, value, text):
    tick()
    element = find_element(by, value)
    element.send_keys(text)
    element.send_keys(Keys.DOWN)
    element.send_keys(Keys.ENTER)

        
def select_from_dropdown(by, value, text):
    tick()
    select = Select(find_element(by, value))
    select.select_by_visible_text(text)

def wait_until(condition, error=None, element=None, **kw):
    try:
        return WebDriverWait(element or driver, wait_timeout, **kw).until(condition)
    except Exception as e:
        print("Timed out!", error or element or driver, file=sys.stderr)
        raise
    
def wait_for_element(*selectorArgs, **kw):
    return wait_until(EC.presence_of_element_located(make_selector(*selectorArgs)), **kw)
    
def wait_for_visible(*selectorArgs, **kw):
    return wait_until(EC.visibility_of_element_located(make_selector(*selectorArgs)), **kw)
    
def wait_for_invisible(*selectorArgs, **kw):
    return wait_until(EC.invisibility_of_element_located(make_selector(*selectorArgs)), **kw)

def wait_for_clickable(*selectorArgs, **kw):
    return wait_until(EC.element_to_be_clickable(make_selector(*selectorArgs)), **kw)

def wait_for_ajax():
    return wait_for_background_flag("jquery.active", error="Ajax operation did not complete")

def wait_for_background_flag(flag_name, error="Background operation did not complete", **kw):
    return wait_until(lambda d: d.execute_script("return " + flag_name + " == 0"), error=error, **kw)

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
    return wait_until(case_insensitive_text_to_be_present_in_element(make_selector(*selectorArgs), text), **kw)

def wait_and_click(*selectorArgs, **kw):
    attempts = 5
    for attempt in range(attempts):
        try:
            element = wait_until(EC.element_to_be_clickable(make_selector(*selectorArgs)), error=repr(selectorArgs[-1]) + " not clickable", **kw)
            time.sleep(0.5)
            element.click()
            return element
        except StaleElementReferenceException:
            if attempt < attempts - 1:
                time.sleep(0.1)
            else:
                raise
        except WebDriverException as e:
            if attempt < attempts - 1 and 'is not clickable at point' in str(e):
                time.sleep(0.1)
            else:
                raise
    
def wait_and_hover_on_element(*selectorArgs):
    action = ActionChains(driver)
    element = wait_for_visible(*make_selector(*selectorArgs))
    action.move_to_element(element).perform()
    return element



def wait_and_move_and_click_on_element(*selectorArgs, modifier=None):
    """
    Waits for an element to be visible, moves to it, and performs a click. Optionally, a modifier key can be held down during the click. Keep in mind in some pipelines the modifier key may not work as expected. Try using the JavaScript version (wait_and_click_element_js) if you encounter issues.

    Parameters:
    *selectorArgs: tuple
        A variable length argument list used to create a selector for the element.
    modifier: str, optional
        A string representing the modifier key to hold down during the click (e.g., 'CONTROL', 'SHIFT', 'ALT'). Default is None.

    Returns:
    WebElement
        The web element that was found and clicked.

    Example:
    wait_and_move_and_click_on_element('my-data-test-id', modifier='CONTROL')
    """
    action = ActionChains(driver)
    element = wait_for_visible(*make_selector(*selectorArgs))

    if modifier is not None:
        actionChain = action.key_down(getattr(Keys, modifier))
        actionChain = actionChain.click(element)
        actionChain = action.key_up(getattr(Keys, modifier))
    else:
        actionChain = action.click(element)

    actionChain.perform()
    return element

def wait_and_click_element_js(*selectorArgs, modifier=None):
    """
    Waits for an element to be visible and performs a click using JavaScript. Optionally, a modifier key can be held down during the click.

    Parameters:
    *selectorArgs: tuple
        A variable length argument list used to create a selector for the element.
    modifier: str, optional
        A string representing the modifier key to hold down during the click (e.g., 'CONTROL', 'SHIFT', 'ALT'). Default is None.

    Returns:
    WebElement
        The web element that was found and clicked.

    Example:
    wait_and_click_element_js('my-data-test-id', modifier='CONTROL')
    """
    selector = make_selector(*selectorArgs)
    element = wait_for_visible(*selector)
    
    if modifier:
        modifier = modifier.lower()
        modifiers = {
            'control': 'ctrlKey',
            'ctrl': 'ctrlKey',
            'shift': 'shiftKey',
            'alt': 'altKey'
        }
        modifier_key = modifiers.get(modifier, '')
        script = f"""
        var element = arguments[0];
        var event = new MouseEvent('click', {{
            bubbles: true,
            cancelable: true,
            view: window,
            {modifier_key}: true
        }});
        element.dispatchEvent(event);
        """
    else:
        script = """
        var element = arguments[0];
        element.click();
        """
    
    driver.execute_script(script, element)
    return element

def wait_and_move_and_context_click_on_element(*selectorArgs):
    """
    Waits for an element to be visible, moves to it, and performs a context click (right-click). Keep in mind in some tests the modifier key may not work as expected. Try using the JavaScript version (wait_and_click_element_js) if you encounter issues.

    Parameters:
    *selectorArgs: tuple
        A variable length argument list used to create a selector for the element.

    Returns:
    WebElement
        The web element that was found and right-clicked.

    Example:
    wait_and_move_and_context_click_on_element('my-data-test-id', modifier='CONTROL')
    """
    action = ActionChains(driver)
    element = wait_for_visible(*make_selector(*selectorArgs))
    action.context_click(element).perform()
    return element

def wait_and_move_and_context_click_on_element_using_js(*selectorArgs):
    """
    Waits for an element to be visible, moves to it, and performs a context click (right-click) using JavaScript.

    Parameters:
    *selectorArgs: tuple
        A variable length argument list used to create a selector for the element. It requires exactly 2 arguments: by and value.

    Raises:
    ValueError
        If the number of arguments provided is not exactly 2.

    Returns:
    WebElement
        The web element that was found and right-clicked.

    Example:
    wait_and_move_and_context_click_on_element_using_js('my-data-test-id', modifier='CONTROL')
    """
    if len(selectorArgs) != 2:
        raise ValueError("wait_and_move_and_context_click_on_element requires exactly 2 arguments: by and value")
    
    by, value = selectorArgs
    element = wait_for_visible(*make_selector(by, value))
    
    # Use JavaScript to trigger the right-click event
    driver.execute_script("""
        (function(element) {
            console.log('Triggering right-click event on element:', element);
            
            // Get the element's bounding rectangle
            var rect = element.getBoundingClientRect();
            
            // Calculate the center coordinates of the element
            var x = rect.left + (rect.width / 2);
            var y = rect.top + (rect.height / 2);
            
            // Create and dispatch the contextmenu event at the center of the element
            var event = new MouseEvent('contextmenu', {
                bubbles: true,
                cancelable: true,
                view: window,
                clientX: x,
                clientY: y
            });
            element.dispatchEvent(event);
        })(arguments[0]);
    """, element)

def send_keyboard(modifier=None, key=None):
    action = ActionChains(driver)
    if modifier != None:
        if key == None:
            actionChain = action.send_keys(getattr(Keys, modifier))
        else:
            actionChain = action.key_down(getattr(Keys, modifier))
            actionChain = actionChain.send_keys(key)
            actionChain = actionChain.key_up(getattr(Keys, modifier))
    else:
        actionChain = action.send_keys(key)
    actionChain.perform()

def tick(factor=1):
    if delay:
        time.sleep(delay * factor)
    
capture_numbered=False
page_number = 0
wait_handler = None
def wait_for_checkpoint(checkpoint_name):
    if wait_handler:
        wait_handler.wait_for_checkpoint(checkpoint_name)
        
def file_is_complete_download(fn):
    if wait_handler:
        return wait_handler.file_is_complete_download(fn)
    else:
        return not fn.endswith(".crdownload") and not fn.endswith(".tmp")

def wait_for_download():
    downloadsDir = get_downloads_dir()
    if downloadsDir:
        for _ in range(wait_timeout * 10):
            files = [ fn for fn in os.listdir(downloadsDir) if file_is_complete_download(fn) ]
            if len(files) > 0:
                return
            else:
                time.sleep(0.1)
    raise WebDriverException("No download files available after waiting " + str(wait_timeout) + " seconds")

def capture_all_text(pagename="websource", element=None, shadow_dom_info=None, checkpoint=True):
    if delay:
        time.sleep(delay)
    if checkpoint:
        wait_for_checkpoint(pagename)
    fn = pagename + ".html"
    if capture_numbered:
        global page_number
        page_number += 1
        fn = str(page_number).zfill(3) + "_" + fn
    while os.path.isfile(fn):
        fn = get_next_fn(fn)
    driver.save_screenshot(fn.replace(".html", ".png"))
    with open(fn, mode="w", encoding="utf-8") as f:
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
browser_console_error_file = sys.stderr
global_error_level = 'WARNING'

loglevels = { 'NOTSET':0 , 'DEBUG':10 ,'INFO': 20 , 'WARNING':30, 'ERROR':40, 'SEVERE':40, 'CRITICAL':50}


def fetch_logs(serious_only, serious_level, clean_empty_browser_errors=True):
    if isinstance(driver, (webdriver.Chrome, webdriver.Edge)):
        # only chrome allows fetching browser logs
        serious_level_number = loglevels.get(serious_level)
        for log_type in driver.log_types:
            for entry in driver.get_log(log_type):
                level = entry['level']
                serious = loglevels.get(level, 99) >= serious_level_number
                try:
                    message = entry['message']
                    parts = shlex.split(message)
                    if parts[0].endswith(".js"): # temporary file reference, add as postfix
                        message = " ".join(parts[2:])
                        file = parts[0].rsplit("/")[-1]
                        message += " (" + file + ":" + parts[1] + ")"
                    message = level + ": " + message
                    if serious:
                        print(message, file=browser_console_error_file)
                    elif not serious_only:
                        timestampSeconds = entry["timestamp"] / 1000
                        timestamp = datetime.fromtimestamp(timestampSeconds).isoformat()
                        print(timestamp, message, file=browser_console_file)
                except Exception as e:
                    print("FAILED to parse browser console message -", str(e), "\nMessage was '" + entry['message'] + "'", file=sys.stderr)

    # Check if browser_console_error_file is not set to sys.stderr and delete if empty to prevent unnecessary empty browser error files.
    if clean_empty_browser_errors and not serious_only and browser_console_error_file != sys.stderr:
        file_path = browser_console_error_file.name
        browser_console_error_file.close()
        if os.path.exists(file_path) and os.path.getsize(file_path) == 0:
            os.remove(file_path)


def close(**kw):
    global driver
    if driver != None:
        if delay:
            time.sleep(delay)
        fetch_logs(serious_only=False, serious_level=global_error_level, **kw)
        driver.quit()
        driver = None
    else:
        print("Couldn't close, driver == None")

