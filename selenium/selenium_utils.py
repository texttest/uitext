
from selenium import webdriver # @UnresolvedImport
from selenium.webdriver.support.ui import WebDriverWait, Select # @UnresolvedImport
from selenium.webdriver.support import expected_conditions as EC # @UnresolvedImport
from selenium.webdriver.common.keys import Keys # @UnresolvedImport
from selenium.common.exceptions import WebDriverException # @UnresolvedImport
from selenium.webdriver.common.by import By # @UnresolvedImport


import os, sys, time

driver = None
orig_url = None
delay = float(os.getenv("USECASE_REPLAY_DELAY", "0"))

def run_with_usecase(url):
    setup(url)
    if os.path.isfile("usecase.py"):
        try:
            exec(compile(open("usecase.py").read(), "usecase.py", 'exec'))
        except Exception:
            close()
            raise

def setup(url):
    global driver, orig_url
    orig_url = url
    options = webdriver.ChromeOptions()
    screen_size = os.getenv("USECASE_SCREEN_SIZE")
    browser_lang = os.getenv("USECASE_UI_LANGUAGE")
    if browser_lang:
        options.add_argument("--lang=" + browser_lang)
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
    return "//*[@data-test-id='" + test_id + "']"

def find_element_by_test_id(test_id):
    return driver.find_element_by_xpath(test_id_xpath(test_id))

def enter_text(testid, text, enter=False):
    textfield = find_element_by_test_id(testid)
    if delay:
        time.sleep(delay)
    textfield.send_keys(Keys.CONTROL, "a")
    textfield.send_keys(text)
    if enter:
        textfield.send_keys(Keys.ENTER)
        
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

    
def tick(factor=1):
    if delay:
        time.sleep(delay * factor)
    
def capture_all_text(pagename="websource"):
    if delay:
        time.sleep(delay)
    fn = pagename + ".html"
    while os.path.isfile(fn):
        fn = get_next_fn(fn)
    with open(fn, mode="w") as f:
        f.write(driver.page_source)
    
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

