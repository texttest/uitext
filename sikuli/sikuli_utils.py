        
import org.sikuli.basics.SikulixForJython  # @UnusedImport
from sikuli import Settings, App, Env, Region, Pattern, Mouse, Location, capture, type, paste, popAsk, Key, SCREEN, uprint, OCR  # @UnresolvedImport
import org.sikuli.script.FindFailed as FindFailed
import org.sikuli.script.SikuliXception as SikuliXception
from java.awt.datatransfer import StringSelection
from java.awt.datatransfer import Clipboard
from java.awt import Toolkit
import shutil, datetime, os, re, sys, subprocess
from glob import glob
import time

def log(msg):
    n = datetime.datetime.now()
    uprint(n.strftime("%H:%M:%S") + "." + str(n.microsecond), ":", msg)
    sys.stdout.flush()

# from time import sleep
Settings.OcrTextRead = True 
Settings.OcrTextSearch = True
Settings.OcrDataPath = os.getenv("SIKULI2")
Settings.OcrReadText = True
Settings.ActionLogs = False
Settings.InfoLogs = False
Settings.MinSimilarity = 0.95  # default 0.7 is a bit too keen to find false positives
Settings.MoveMouseDelay = float(os.getenv("USECASE_REPLAY_DELAY", "0"))
OCR.globalOptions().variable("debug_file", os.path.abspath("tesseract.log"))
OCR.globalOptions().dataPath(os.getenv("SIKULI2"))
OCR.globalOptions().language(os.getenv("USECASE_UI_LANGUAGE", "eng"))
# Settings.MinSimilarity = 0.1

app = None

def dump_clipboard_to_file(fn):
    text = Env.getClipboard()
    if text:
        open(fn, "wb").write(text.encode("utf-8"))

def clear_clipboard():
    toolkit = Toolkit.getDefaultToolkit()
    clipboard = toolkit.getSystemClipboard()
    clipboard.setContents(StringSelection(""), None)

def press_navigation_key(*args):
    # Need the delay also so we can see what's happening. This is a "mouse equivalent" action
    time.sleep(Settings.MoveMouseDelay)
    type(*args)
    
def restore_mouse():
    Mouse.move(Location(0, 0))
    
def start_app():
    global app
    OCR.status()
    # Avoid trouble with tooltips depending on where mouse was before
    restore_mouse()
    app = App(sys.argv[1])
    if len(sys.argv) > 2:
        cmdLine = subprocess.list2cmdline(sys.argv[2:])
        if "SUT_ENCODING" in os.environ:
            # Jython seems to convert command line arguments to UTF-8, whether you like it or not
            # Provide a hook to put them back...
            cmdLine = unicode(cmdLine, "utf-8").encode(os.getenv("SUT_ENCODING"))
        app.setUsing(cmdLine)
    app.open()
    app.focus()

def wait_for_app_to_terminate():
    while app.isRunning(0):
        time.sleep(1)

def find_window(title, exeFile):
    global app
    if app is not None:
        # we already set it up, no need to do anything
        return
    # app = App.open(" ".join(sys.argv[1:]))
    # app.focus()
    for i in range(5):
        app = App.focus(title)
        win = App.focusedWindow()
        appStr = repr(app)
        if win is not None:
            if exeFile in appStr:
                log("Using App " + appStr + " with window " + repr(win))
                win.click()
                return win
            else:
                tmpFile = capture(SCREEN)
                shutil.move(tmpFile, "rejected_app_" + str(i + 1) + ".png")
                log("Rejecting " + appStr + " not matching exe file '" + exeFile + "'")
                
                
        time.sleep(1)
    terminate_with_screenshot("Failed to find window with title '" + title + "' or exe file '" + exeFile + "' after 5 attempts!")
    
def close_window():
    if app is not None:
        log("Caught exception, closing app")
        app.close(1) # wait 1 second for response, kill if nothing happening
        pid = app.getPID()
        if pid != -1:
            # Application might refuse to close, kill it if so
            log("App refusing to close, killing process " + str(pid))
            subprocess.call([ "taskkill", "/f", "/pid", str(pid) ])

def substrings(inputStr, maxSize):
    length = len(inputStr)
    result = [inputStr[i:j + 1] for i in xrange(length - maxSize + 1) for j in xrange(i + maxSize - 1, length)]
    result.sort(key=len, reverse=True)
    return result

def findRegionOCR(label, searchArea, recurse=True, timeout=1):
    win = getWindow()
    try:
        log(": Searching for OCR text " + label + " in " + repr(searchArea) + "timeout=" + repr(timeout))
        region = searchArea.waitText(label, timeout)
    except FindFailed:
        uprint(datetime.datetime.now().strftime("%H:%M:%S.%f"), ": Failed to find OCR text", label, "in", repr(searchArea))
        if getWindow().getH() != win.getH():
            print "Window changed, try same text"
            return findRegionOCR(label, searchArea)
        if recurse and " " in label:
            for word in label.split(" "):
                if len(word) >= 5:
                    print "Word split, try", word.encode("utf-8")
                    region = findRegionOCR(word, searchArea, recurse=False, timeout=0)
                    if region:
                        return region
        if recurse and len(label) > 5:
            for word in sorted(label.split(" "), key=len, reverse=True):  # longest words first...
                for subLabel in substrings(word, 5):
                    region = findRegionOCR(subLabel, searchArea, recurse=False, timeout=0)
                    if region:
                        return region
            print "Giving up!"
            return
        else:
            print "Giving up!"
            return
        
    uprint(datetime.datetime.now().strftime("%H:%M:%S.%f"), ": Found OCR region for", label, "=", repr(region))
    return region

def getWindow(dialogRatio=None):
    for i in range(100):
        win = app.window(i)
        if win is None:
            return
        
        log("Check window " + str(i) + ": " + repr(win))
        if win.getH() > 10 and (dialogRatio is None or win.getH() * dialogRatio < SCREEN.getH()):
            return win

def waitForDialogToDisappear(maxSeconds=10, dialogRatio=1.5, preexisting=False):
    # For progress dialogs etc
    # Assume these are less than half of the height of the screen
    hadDialog = preexisting
    currDialog = None
    for _ in range(maxSeconds * 10):
        currDialog = getWindow(dialogRatio)
        dialogActive = currDialog is not None
        hadDialog |= dialogActive
        if hadDialog and not dialogActive:
            return True
        else:
            time.sleep(0.1)
    uprint("Dialog still present at", repr(currDialog))
    return False

def waitForWindowToAppear(**kw):
    return waitForDialogToAppear(dialogRatio=None, **kw)

def waitForDialogToAppear(maxSeconds=10, dialogRatio=3):
    # For progress dialogs etc
    # Assume these are less than a third of the height of the screen
    currDialog = None
    for _ in range(maxSeconds * 10):
        currDialog = getWindow(dialogRatio)
        if currDialog is not None:
            return currDialog
        else:
            time.sleep(0.1)


def takeHighlightedScreenshot(fileName, highlightArea):
    # highlightArea.highlight()
    r = " (" + str(highlightArea.getX()) + "," + str(highlightArea.getY()) + " " + str(highlightArea.getW()) + "x" + str(highlightArea.getH()) + ")"
    shutil.move(capture(SCREEN), fileName + r + ".png")
    # highlightArea.highlight()
 

def findRegionFromImages(label, imageFiles, searchArea, timeout=1, override_similarity=None, **kw):
    for imageFile in sorted(imageFiles):
        try:
            log("Searching for image " + label + " in " + repr(searchArea) + " timeout=" + repr(timeout))
            if override_similarity is None:
                region = searchArea.wait(imageFile, timeout)
            else:
                pattern = Pattern(imageFile).similar(override_similarity)
                region = searchArea.wait(pattern, timeout)
            log("Found image region for " + label + " = " + repr(region))
            # print "Text was", region.text().encode("utf-8")
            return region
        except (FindFailed, SikuliXception):
            pass
            
    takeHighlightedScreenshot("screenshot_Failed to find image region for " + label, searchArea)
    log("Failed to find image region for " + label + " in " + repr(searchArea))

    
class BadHintsFile(RuntimeError):
    pass


def readHint(line):
    regex = re.compile("hint=([0-9]*)-([0-9]*) of ([0-9]*)")
    match = regex.search(line)
    if match is not None:
        pos1, pos2, size = [ int(match.group(i)) for i in range(1, 4)]
        return pos1, pos2 - pos1, size
    else:
        raise BadHintsFile, "Could not parse line in hints file: " + line


def getHintArea(hintsFile):
    f = open(hintsFile)
    try:
        xPos, width, oldWindowWidth = readHint(f.readline())
        yPos, height, oldWindowHeight = readHint(f.readline())
    finally:
        f.close()
    win = getWindow()
    if xPos > win.getW():
        xPos -= oldWindowWidth - win.getW()
    if yPos > win.getH():
        yPos -= oldWindowHeight - win.getH()
    xPos += win.getX()
    yPos += win.getY()
    if xPos < 0 or yPos < 0:
        raise BadHintsFile, "Window size too different, could not make sense of hints file"
    hintArea = Region(xPos, yPos, width, height)
    return hintArea

def findHintAreas(hintsFile, boundingBox=None):
    boundingBox = boundingBox or getWindow()
    if boundingBox is None:
        app.focus()
        boundingBox = waitForWindowToAppear()
        if boundingBox is None:
            terminate_with_screenshot("Could not find any application window after waiting 10 seconds, something is seriously wrong!")
            
    areas = [ (boundingBox, boundingBox, False) ]
    if not os.path.isfile(hintsFile):
        return areas
    
    try:
        hintArea = getHintArea(hintsFile)
        searchArea = hintArea.nearby(20)
        areas.insert(0, (hintArea, searchArea, True))  # try this before the whole window
    except BadHintsFile, e:
        sys.stderr.write("ERROR: could not parse hints file at " + hintsFile + "\n" + str(e) + "\n")
    return areas

def handleAnswer(answer):
    if not answer:
        return False
            
    # app.focus()# Must switch back to the app before proceeding
    # Hardcoding database name not ideal, but this doesn't work in Sikuli currently, see
    # https://answers.launchpad.net/sikuli/+question/266528
    app.focus()
    return True

def assumeInteractive():
    # Could be running TextTest, Jenkins... add as appropriate
    ci_vars = [ "TEXTTEST_BATCH_SESSION", "BUILD_NUMBER" ]
    return not any((var in os.environ for var in ci_vars))

def askForNewImage(label, locatorDir):
    if not assumeInteractive():
        return False
    msg = u"Hittade inte texten '" + label + u"' i GUI:t.\n" + \
            u"För att fortsätta, ta en screenshot i png format, och lägg den i foldern\n" + \
            locatorDir + "\n"\
            u"Ska vi fortsätta?"
    answer = popAsk(msg, title="Hittade inte texten")
    return handleAnswer(answer)

def askIfHintCorrect(hintArea, label):
    if not assumeInteractive():
        return False
    hintArea.highlight()
    msg = u"Hittade varken texten '" + label + u"' eller de lagrade bilderna i GUI:t.\n" + \
            u"Vi har tidigare lagrat regionen som visas med röd ram i fönstret just nu.\n" + \
            u"Ska vi ta en ny screenshot där automatiskt, klicka där, och fortsätta med testet?"
    answer = popAsk(msg, title="Hittade varken texten eller bilderna")
    hintArea.highlight()
    return handleAnswer(answer)
        
def getLocatorDir(label):
    locatorDir = os.path.join(os.getenv("USECASE_LOCATOR_ROOT"), label)
    if not os.path.isdir(locatorDir):
        os.makedirs(locatorDir)
    return locatorDir

def combineRegions(newReg, oldReg):
    x1 = min(newReg.getX(), oldReg.getX())
    y1 = min(newReg.getY(), oldReg.getY())
    x2 = max(newReg.getX() + newReg.getW(), oldReg.getX() + oldReg.getW())
    y2 = max(newReg.getY() + newReg.getH(), oldReg.getY() + oldReg.getH())
    width = x2 - x1
    height = y2 - y1
    growthFactor = float(width * height) / (oldReg.getW() * oldReg.getH())
    # Only want to do this if it's more or less nearby. Area shouldn't become enormous if something moves a long way
    if growthFactor < 5.0:
        combined = Region(x1, y1, width, height)
        print "Combined region with growth factor", growthFactor, "using new region at", combined, "based on", oldReg, "and", newReg
        return combined
    else:
        # Otherwise, just assume it's moved and discard the old region
        print "Combined region with growth factor", growthFactor, "which is too large. Using", newReg, "and discarding", oldReg
        return newReg

def getBasicTimeout(failureExpected, defaultTimeout):
    return defaultTimeout or (0.1 if failureExpected else 2)
    
def getTimeout(*args):
    basicTimeout = getBasicTimeout(*args)
    # Batch session: don't worry about speed. Interactive: better to be fast and a bit less reliable.
    return basicTimeout if assumeInteractive() else basicTimeout * 3
    
def findRegionFromImagesInHintAreas(imageFiles, hintAreas, label, timeout, **kw):
    if imageFiles:
        for hintArea, searchArea, fromFile in hintAreas:
            region = findRegionFromImages(label, imageFiles, searchArea, timeout=timeout, **kw)
            if region:
                return region, hintArea, fromFile, True
    return None, None, None, False
    
def findRegionFromOCRInHintAreas(hintAreas, label, exact, timeout, **kw):
    for hintArea, searchArea, fromFile in hintAreas:
        region = findRegionOCR(label, searchArea, recurse=not exact, timeout=timeout)
        if region:
            return region, hintArea, fromFile, False
    return None, None, None, False
                
def findRegionUsingImagesOrOcr(hintsFile, imageFiles, label, exact, failureExpected, boundingBox=None, defaultTimeout=None, **kw):
    hintAreas = findHintAreas(hintsFile, boundingBox)
    timeout = getTimeout(failureExpected, defaultTimeout)
    region, hintArea, fromFile, fromImage = findRegionFromImagesInHintAreas(imageFiles, hintAreas, label, timeout=timeout, **kw)
    if not region and (not failureExpected or not imageFiles):
        region, hintArea, fromFile, fromImage = findRegionFromOCRInHintAreas(hintAreas, label, exact, timeout=timeout, **kw)
    if region:
        uprint("Hint Area was", repr(hintArea))
        if not fromFile and os.path.isfile(hintsFile):
            print "Position hints were wrong, regenerating them"
            os.remove(hintsFile)  # Found in whole window, but not region -> hints file wrong, remove it
            if len(hintAreas) == 2: 
                # Assume the exact location varies a bit, expand the search area
                combinedRegion = combineRegions(region, hintAreas[0][0])
                writeHintsFile(hintsFile, combinedRegion)
    return region, fromImage
    
def takeScreenshot(locatorDir, region, fromPosition):
    captureRegion = region if fromPosition else region.nearby(3)  # OCR tends to return a too-close-in region that it then can't interpret itself
    tmpFile = capture(captureRegion)
    shutil.move(tmpFile, os.path.join(locatorDir, os.path.basename(tmpFile)))


def writeHintsFile(hintsFile, region):
    f = open(hintsFile, "w")
    win = getWindow()
    xPos = region.getX() - win.getX()
    xPos2 = xPos + region.getW()
    f.write("xhint=" + str(xPos) + "-" + str(xPos2) + " of " + str(win.getW()) + "\n")
    yPos = region.getY() - win.getY()
    yPos2 = yPos + region.getH()
    f.write("yhint=" + str(yPos) + "-" + str(yPos2) + " of " + str(win.getH()) + "\n")
    f.close()

def getImageFiles(locatorDir):
    return glob(os.path.join(locatorDir, "*.png"))

def findRegionWithWidget(label, searchRegion=None, timeout=1, failureExpected=False):
    # No text or positions here, just have to cope...
    locatorDir = getLocatorDir(os.path.join("widgets", label))
    imageFiles = getImageFiles(locatorDir)
    # Widgets have no text and they look a bit different in different settings, best to be generous
    region = findRegionFromImages(label, imageFiles, searchRegion or getWindow(), timeout, override_similarity=0.7)
    if not region and not failureExpected:
        if askForNewImage(label, locatorDir):
            return findRegionWithWidget(label, searchRegion, timeout)
        else:
            shutil.move(capture(searchRegion), "screenshot_findRegionWithWidget.png")
            terminate_with_screenshot("Failed to find widget for '" + label + "', terminating")
    return region


def terminate_with_screenshot(errorMsg):
    tmpFile = capture(SCREEN)
    shutil.move(tmpFile, "screenshot_on_termination.png")
    print errorMsg
    open("sikuli_actions.log", "w").write(errorMsg.encode("utf-8") + "\n")
    close_window()
    sys.exit(1)

def findRegionWithText(label, exact=False, failureExpected=False, **kw):
    locatorDir = getLocatorDir(label)
    hintsFile = os.path.join(locatorDir, "search_hints.txt")
    imageFiles = getImageFiles(locatorDir)
    
    region, fromImage = findRegionUsingImagesOrOcr(hintsFile, imageFiles, label, exact, failureExpected, **kw)
    fromPosition = False         
    if not region and not failureExpected:                
        # We had an image, and a position, but still didn't find it
        if imageFiles and os.path.isfile(hintsFile):
            hintArea = getHintArea(hintsFile)
            hintOcr = hintArea.text()  # shouldn't be relevant, but it's a different algorithm and has been known to work when OCR search fails
            if hintOcr == label or askIfHintCorrect(hintArea, label):  # text still matches in hint region, or user says it's OK, accept and take new screenshot
                region = hintArea
                fromPosition = True
                
        if not region and askForNewImage(label, locatorDir):
            return findRegionWithText(label, exact, **kw)
    
    if region:  # Succeeded, build a multilocator to aid future searches
        if not fromImage:  # didn't use image, take a screenshot
            takeScreenshot(locatorDir, region, fromPosition)
        
        if not os.path.isfile(hintsFile):  # didn't use hint, record the position
            writeHintsFile(hintsFile, region)
        return region
    elif not failureExpected:
        # Terminate if we can't make progress, don't keep looking for stuff...
        terminate_with_screenshot("Failed to find locator for '" + label + "', terminating")

def closeOnException(method, *args, **kw):
    try:
        return method(*args, **kw)
    except:
        if app is not None:
            app.close()
        raise
    
def tabAndType(texts):
    for text in texts:
        press_navigation_key(Key.TAB)
        type(text)
    
def tabAndPaste(texts):
    for text in texts:
        press_navigation_key(Key.TAB)
        paste(text)

def tabAndSelect(count=1):
    for _ in range(count):
        press_navigation_key(Key.TAB)  # choose the first
        press_navigation_key(Key.DOWN)  # choose the first    


def clickInField(label, scaleFactor=2, orientation="below", **kw):
    region = closeOnException(findRegionWithText, label, **kw)
    if region is not None:
        method = getattr(region, orientation)
        boxSize = region.getH() if orientation == "below" else region.getW()
        box = method(int(boxSize * scaleFactor))
        box.click()
        restore_mouse()
        return box

def fillTextField(label, text, scaleFactor=2, paste_in=False, **kw):
    box = clickInField(label, scaleFactor, **kw)
    if paste_in:
        paste(text)
    else:
        type(text)
    return box
        
def fillDateField(label, text, scaleFactor=2, **kw):
    box = clickInField(label, scaleFactor, **kw)  # Click somewhere on the date. Could be year, month or day
    if box is not None:
        type(Key.F4)  # open the date picker
        type(Key.ENTER)  # close it again. Now we're on the year...
        type(text)
    return box
        
def clickText(label, **kw):
    region = closeOnException(findRegionWithText, label, **kw)
    if region is not None:
        region.click()
        restore_mouse()
    return region

def clickWidget(label, **kw):
    region = closeOnException(findRegionWithWidget, label, **kw)
    if region is not None:
        region.click()
        restore_mouse()
    return region

def clickCheckbox(label, widgetName, orientation="left", searchBoxSize=100, widgetLabel=False, searchRegion=None, **kw):
    if widgetLabel: 
        region = closeOnException(findRegionWithWidget, label, searchRegion=searchRegion, **kw)
    else:
        region = closeOnException(findRegionWithText, label, boundingBox=searchRegion, **kw)
    if region is not None:
        method = getattr(region, orientation)
        box = method(searchBoxSize).nearby(10)  # Big enough to contain the checkbox, without accidentally containing some others also...
        return clickWidget(widgetName, searchRegion=box)

def toggleGroupRadioButton(groupLabel, scaleFactor=2, label="", allButtonsTextLength=None, **kw):
    region = closeOnException(findRegionWithText, groupLabel, **kw)
    if allButtonsTextLength and allButtonsTextLength > len(groupLabel): # guess for text size of buttons + labels
        factor = float(allButtonsTextLength) / len(groupLabel)
        extra = int(region.getW() * factor) - region.getW()
        region = region.grow(0, extra, 0, 0)
    below = region.below(int(region.getH() * scaleFactor))
    box = below.nearby(10)
    if label:
        return enableRadioButton(label, searchRegion=box, **kw)
    else:
        return clickWidget("radio button (unchecked)", searchRegion=box)
    
def enableRadioButton(label, **kw):
    return clickCheckbox(label, "radio button (unchecked)", **kw)

def enableCheckbox(label, **kw):
    return clickCheckbox(label, "checkbox (unchecked)", **kw)
    
def disableCheckbox(label, **kw):
    return clickCheckbox(label, "checkbox (checked)", **kw)

def choose_default_from_dropdown(tabOnwards=True):
    type(Key.F4)  # show the list, don't delay
    press_navigation_key(Key.DOWN)  # choose the first
    press_navigation_key(Key.ENTER)  # select it
    if tabOnwards:
        press_navigation_key(Key.TAB)  # move along

def choose_from_dropdown(position=1):
    type(Key.F4)  # show the list, don't delay
    for _ in range(position): 
        press_navigation_key(Key.DOWN)  # choose the first
    press_navigation_key(Key.ENTER)  # select it
            
def selectDefaultDropDown(labelAbove=None, scaleFactor=2, tabOnwards=False, **kw):
    if labelAbove is not None:
        region = closeOnException(findRegionWithText, labelAbove, **kw)
        if region is not None:
            box = region.below(int(region.getH() * scaleFactor))
            box.click()
            choose_default_from_dropdown(tabOnwards)
        
def selectDropDown(labelAbove=None, position=1, scaleFactor=2, **kw):
    if labelAbove is not None:
        region = closeOnException(findRegionWithText, labelAbove, **kw)
        if region is not None:
            box = region.below(int(region.getH() * scaleFactor))
            box.click()
            if position > 0:
                choose_from_dropdown(position)
        
def selectFromDropDown(label, labelAbove=None, **kw):
    searchRegion = None
    if labelAbove is not None:
        region = closeOnException(findRegionWithText, labelAbove, **kw)
        if region is not None:
            win = getWindow()
            searchWidth = win.getX() + win.getW() - region.getX()
            searchHeight = min(win.getY() + win.getH() - region.getY(), region.getH() * 5)  # don't search too far from the label
            searchRegion = Region(region.getX(), region.getY(), searchWidth, searchHeight)
        clickWidget("drop-down arrow", searchRegion=searchRegion)
    else:
        type(Key.F4)  # open the dropdown in current location
    time.sleep(0.5) # Wait for the dropdown to 'slide' otherwise we can find our text while it's on the way down and then click the one above...
    clickText(label, **kw)
    
def wait_for_widget_to_appear(widget_name, copy_text=False, expand_all=0):
    for _ in range(20):
        region = findRegionWithWidget(widget_name, failureExpected=True)
        if region:
            for i in range(expand_all):
                if i > 0:
                    time.sleep(0.5)
                clickWidget("expander")
            if copy_text:
                region.click()
                press_navigation_key("a", Key.CTRL)
                press_navigation_key("c", Key.CTRL)
            return
    terminate_with_screenshot("No " + repr(widget_name) + " found after 20 seconds of searching, terminating")
    
def wait_for_text_to_appear(label):
    for _ in range(20):
        region = findRegionWithText(label, failureExpected=True)
        if region:
            return
    terminate_with_screenshot("No " + repr(label) + " found after 20 seconds of searching, terminating")
    
