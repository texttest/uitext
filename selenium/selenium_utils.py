
from selenium import webdriver # @UnresolvedImport
from selenium.webdriver.support.ui import WebDriverWait, Select # @UnresolvedImport
from selenium.webdriver.support import expected_conditions as EC # @UnresolvedImport
from selenium.webdriver.common.keys import Keys # @UnresolvedImport
from selenium.common.exceptions import WebDriverException, NoSuchShadowRootException, StaleElementReferenceException # @UnresolvedImport
from selenium.webdriver.common.by import By # @UnresolvedImport


import os, sys, time

driver = None
orig_url = None
delay = float(os.getenv("USECASE_REPLAY_DELAY", "0"))
test_id_key = "id"
add_explicit_display_tags = False

def run_with_usecase(url):
    setup(url)
    if os.path.isfile("usecase.py"):
        try:
            exec(compile(open("usecase.py").read(), "usecase.py", 'exec'))
        except Exception:
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
    global driver, orig_url
    orig_url = url
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
    desired_capabilities['loggingPrefs'] = {'browser':'ALL'}
    driver = webdriver.Chrome(desired_capabilities=desired_capabilities, options=options)
    driver.get(url)
    
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

def enter_text(testid, text, enter=False):
    textfield = find_element_by_test_id(testid)
    enter_text_in_field(textfield, text, enter=enter)
    
def enter_text_in_field(textfield, text, enter=False):
    if delay:
        time.sleep(delay)
    textfield.send_keys(Keys.CONTROL, "a")
    textfield.send_keys(text)
    if enter:
        textfield.send_keys(Keys.ENTER)

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

def find_shadow_dom_info():
    info = []
    for element in driver.find_elements(By.CSS_SELECTOR, "*"):
        if add_explicit_display_tags:
            make_display_explicit(element)
        try:
            shadow_root = element.shadow_root
            content = find_shadow_content(shadow_root)
            info.append((element, content))
        except NoSuchShadowRootException:
            continue
    return info


def add_all_display_tags():
    for element in driver.find_elements(By.CSS_SELECTOR, "*"):
        if add_explicit_display_tags:
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
        
def select_from_dropdown(testid, text):
    tick()
    select = Select(find_element_by_test_id(testid))
    select.select_by_visible_text(text)

def wait_until(condition):
    try:
        return WebDriverWait(driver, 30).until(condition)
    except Exception as e:
        sys.stderr.write("Timed out!" + repr(driver) + "\n")
        close()
        raise
    
def wait_for_visible(*selectorArgs):
    wait_until(EC.visibility_of_element_located(selectorArgs))

def wait_for_clickable(*selectorArgs):
    wait_until(EC.element_to_be_clickable(selectorArgs))

def wait_for_ajax():
    wait_until(lambda d: d.execute_script("return jquery.active == 0"))

def wait_and_click(*selectorArgs):
    for _ in range(5):
        try:
            element = wait_until(EC.element_to_be_clickable(selectorArgs))
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
        for _ in range(100):
            files = [ fn for fn in os.listdir(downloadsDir) if not fn.endswith(".crdownload") ]
            if len(files) > 0:
                return
            else:
                time.sleep(0.1)
    
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
    
def close():
    global driver
    if driver != None:
        if delay:
            time.sleep(delay)
        for entry in driver.get_log('browser'):
            actualMessage = " ".join(entry['message'].split(" ")[2:])
            try:
                sys.stderr.write(eval(actualMessage) + '\n')
            except:
                sys.stderr.write("FAILED to parse " + entry['message'] + '!\n')
        driver.quit()
        driver = None
    else:
        print("Couldn't close, driver == None")

