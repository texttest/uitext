'''
Created on 27 nov. 2017

@author: E601429

'''

import sys, os
from html.parser import HTMLParser
from gridformatter import GridFormatter, GridFormatterWithHeader
from traceback import format_exception
from html.entities import name2codepoint
import argparse

def getExceptionString():
    return "".join(format_exception(*sys.exc_info()))


def get_attr_value(attrs, name):
    for attr, val in attrs:
        if attr == name:
            return val

def getUnderline(text):
    prevNewLinePos = text.rfind("\n")
    lineLen = len(text) - prevNewLinePos - 1
    return "\n" + "=" * lineLen + "\n\n"

def shouldAddWhitespace(text, existingText):
    if len(existingText) == 0:
        return False
    
    lastChar = existingText[-1]
    if text.startswith("\n"):
        return lastChar != "\n"
    else:
        return not lastChar.isspace()


class HtmlExtractParser(HTMLParser):
    def __init__(self, toIgnore=set(), iconProperties=set(), show_invisible=False):
        HTMLParser.__init__(self)
        self.currentSubParsers = []
        self.inBody = False
        self.inScript = False
        self.inSuperscript = False
        self.linkStart = None
        self.text = ""
        self.liLevel = 0
        self.propertiesToIgnore = toIgnore
        self.iconProperties = iconProperties
        self.ignoreUntilCloseTag = ""
        self.ignoreRecursionLevel = 0
        self.show_invisible = show_invisible

    def parse(self, text):
        try:
            self.feed(text)
        except:
            sys.stderr.write("Failed to parse browser text:\n")
            sys.stderr.write(getExceptionString())
            sys.stderr.write("Original text follows:\n")
            sys.stderr.write(text + "\n")
        return self.text

    def getElementProperties(self, attrs):
        cls = get_attr_value(attrs, "class")
        elementProperties = set(cls.split()) if cls else set()
        for idAttr in [ "id", "data-test-id" ]:
            id = get_attr_value(attrs, idAttr)
            if id in self.iconProperties:
                elementProperties.add(id)
        return elementProperties

    def get_icon_name(self, elementProperties):
        is_icon = "icon" in elementProperties
        if is_icon:
            elementProperties.remove("icon")
        
        chosenProperties = self.iconProperties & elementProperties
        if not is_icon or len(chosenProperties) > 0:
            elementProperties = chosenProperties
        if elementProperties:
            shortnames = [ name.split("__")[-1] for name in elementProperties ]  
            return ":" + " ".join(sorted(shortnames)) + ":"
        else:
            return ""
        
    def is_invisible(self, attrs):
        return not self.show_invisible and get_attr_value(attrs, "style") == "display: none;"

    def handle_starttag(self, rawname, attrs):
        name = rawname.lower()
        elementProperties = self.getElementProperties(attrs)
        if self.ignoreUntilCloseTag:
            if self.ignoreUntilCloseTag == name:
                self.ignoreRecursionLevel += 1
        elif not self.propertiesToIgnore.isdisjoint(elementProperties) or self.is_invisible(attrs) or name == "noscript": # If Javascript is disabled then we won't be able to test it anyway...
            self.ignoreUntilCloseTag = name
            self.ignoreRecursionLevel = 1
        elif name == "table":
            if not self.text.endswith("\n"):
                self.text += "\n"
            self.currentSubParsers.append(TableParser())
        elif name == "select":
            if not self.text.endswith("\n"):
                self.text += "\n"
            self.currentSubParsers.append(SelectParser())
        else:
            if name == "svg":
                label = get_attr_value(attrs, "aria-labelledby")
                if label:
                    self.handle_data(":" + label + ":")
                self.ignoreUntilCloseTag = name
                self.ignoreRecursionLevel = 1
            elif elementProperties and (name == "i" or not self.iconProperties.isdisjoint(elementProperties)):
                self.handle_data(self.get_icon_name(elementProperties))
            elif name == "img":
                self.handle_data("Image '" + os.path.basename(get_attr_value(attrs, "src")) + "'")
            elif name == "iframe":
                self.handle_data("IFrame '" + get_attr_value(attrs, "src") + "'")

            if name == "button":
                self.handle_data("Button '")
            elif name == "nav":
                self.addText("\n(Navigation:\n")
            elif name == "li":
                indent = ""
                if self.liLevel > 1:
                    self.addText("\n")
                    indent = "  " * self.liLevel
                self.addText(indent + "- ")
                self.liLevel += 1
            elif name == "br":
                self.addText("\n")
            elif name == "input":
                input_type = get_attr_value(attrs, "type")
                if input_type in ("text", "datetime-local"):
                    text = "=== "
                    placeholder = get_attr_value(attrs, "placeholder")
                    if placeholder:
                        text += "_" + placeholder + "_"
                    text += " ==="
                    if input_type == "datetime-local":
                        text += " (datetime-local)"
                    self.addText(text)
                elif input_type == "button":
                    value = get_attr_value(attrs, "value")
                    self.handle_data("Button '" + value + "'")
                elif input_type == "radio":
                    self.handle_data("( ) ")
            elif name == "textarea":
                self.addText("\n" + "=" * 10 + "\n")
            elif name == "b":
                self.addText("*")
            elif name == "sup":
                self.inSuperscript = True
                self.addText("^")
            elif self.currentSubParsers:
                self.currentSubParsers[-1].startElement(name, attrs)
            elif name == "body":
                self.inBody = True
            elif name == "script":
                self.inScript = True
            elif name == "hr":
                if not self.text.endswith("\n"):
                    self.text += "\n"
                self.text += "_" * 100 + "\n"
            elif name == "a":
                self.linkStart = len(self.text)
            elif name == "div" and not self.text.endswith("\n"):
                self.text += "\n"
            elif self.text.strip() and name in [ "h1", "h2", "h3", "h4" ]:
                while not self.text.endswith("\n\n"):
                    self.text += "\n"

    def handle_endtag(self, rawname):
        name = rawname.lower()
        if self.ignoreUntilCloseTag:
            if self.ignoreUntilCloseTag == name:
                self.ignoreRecursionLevel -= 1
                if self.ignoreRecursionLevel == 0:
                    self.ignoreUntilCloseTag = ""
        elif name in [ "select", "table" ]:
            parser = self.currentSubParsers.pop()
            currText = parser.getText()
            if self.currentSubParsers:
                self.currentSubParsers[-1].addText(currText)
            else:
                self.text += currText
                if not currText.endswith("\n"):
                    self.text += "\n"
        elif name == "button":
            self.handle_data("'")
        elif name == "sup":
            self.inSuperscript = False
        elif name == "b":
            self.addText("*")
        elif name == "li":
            self.liLevel -= 1
            self.addText("\n")
        elif name == "nav":
            self.addText(")")
        elif name == "textarea":
            self.addText("\n" + "=" * 10)
        elif self.currentSubParsers and name != "img":
            self.currentSubParsers[-1].endElement(name)
        elif name == "script":
            self.inScript = False
        elif name in [ "h1", "h2", "h3", "h4" ]:
            self.text += getUnderline(self.text)
        elif name == "a":
            linkText = self.text[self.linkStart:].strip()
            if "\n" in linkText:
                # make sure multiline links hang together
                self.text = self.text[:self.linkStart] + "\n"
                lines = linkText.splitlines()
                width = max((len(line) for line in lines))
                for line in lines:
                    self.text += line.ljust(width) + "->\n"
            else:
                self.text = self.text[:self.linkStart] + linkText + "->  "
            self.linkStart = None
        
    def fixWhitespace(self, line):
        if self.inSuperscript:
            return line.strip()
        while "  " in line:
            line = line.replace("  ", " ")
        return line

    def handle_data(self, content):
        if not self.ignoreUntilCloseTag:
            newLines = [ line.rstrip("\t\r\n") for line in content.splitlines() ]
            self.addText(self.fixWhitespace(" ".join(newLines)))
        
    def needs_space(self, text, origText):
        if len(origText) == 0 or len(text) == 0:
            return False
        
        return text[0].isalnum() and origText[-1].isalnum()
        
    def addText(self, text):
        if self.currentSubParsers:
            self.currentSubParsers[-1].addText(text)
        elif self.inBody and not self.inScript:
            if not text.isspace() or shouldAddWhitespace(text, self.text):
                if self.needs_space(text, self.text):
                    self.text += " "
                self.text += text

class SelectParser:
    def __init__(self):
        self.options = []
        self.inOption = False
        
    def startElement(self, name, attrs):
        if name == "option":
            self.options.append("")
            self.inOption = True
            
    def endElement(self, name):
        if name == "option":
            self.inOption = False
            
    def addText(self, text):
        if self.inOption:
            self.options[-1] += text

    def getText(self):
        return "Dropdown (" + ", ".join(self.options) + ")"


class TableParser:
    def __init__(self):
        self.headerRows = []
        self.currentRow = None
        self.currentRowIsHeader = True
        self.grid = []
        self.activeElements = {}

    def isCell(self, name):
        return name in ["td", "th"]
    
    def isRow(self, name):
        return name in ["tr", "thead"]

    def startElement(self, name, attrs):
        self.activeElements[name] = attrs
        if self.isRow(name):
            self.currentRow = []
        elif self.isCell(name):
            if self.currentRow is None:
                sys.stderr.write("ERROR: Received '" + name + "' element in unexpected context (no table row). Attrs = " + repr(attrs) + "\n")
                sys.stderr.write("Grid so far = " + repr(self.grid) + "\n")
            else:
                self.currentRow.append("")
                if name == "td" and "thead" not in self.activeElements:
                    self.currentRowIsHeader = False
            
    def endElement(self, name):
        if name in self.activeElements:  # Don't fail on duplicated end tags
            if self.currentRow is not None and self.isCell(name):
                colspan = get_attr_value(self.activeElements[name], "colspan")
                if colspan:
                    for _ in range(int(colspan) - 1):
                        self.currentRow.append("")
            del self.activeElements[name]
            if self.isRow(name) and self.currentRow is not None:
                if len(self.currentRow):
                    if self.currentRowIsHeader:
                        self.headerRows.append(self.currentRow)
                    else:
                        self.grid.append(self.currentRow)
                self.currentRow = None
            if name in [ "h1", "h2", "h3", "h4"] and self.currentRow:
                self.addText(getUnderline(self.currentRow[-1]))
        
    def getText(self):
        if len(self.grid) == 0:
            return ""
        
        columnCount = max((len(r) for r in self.grid))
        if self.headerRows:
            columnCountHeader = max((len(r) for r in self.headerRows))
            columnCount = max(columnCountHeader, columnCount)
            formatter = GridFormatterWithHeader(self.headerRows, self.grid, columnCount, allowHeaderOverlap=True)
        else:
            formatter = GridFormatter(self.grid, columnCount)
        return str(formatter)
    
    def isSpaces(self, text):
        return len(text) and all((c == " " for c in text))
            
    def addText(self, text):
        if self.currentRow is not None:
            if len(self.currentRow):
                if text.strip() or shouldAddWhitespace(text, self.currentRow[-1]):
                    self.currentRow[-1] += text
            elif text.strip():
                self.currentRowIsHeader = False
                self.currentRow.append(text)

def parseList(text):
    return set(text.split(",")) if text else set()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Program to write HTML as ASCII art, suitable for e.g. TextTest testing')
    parser.add_argument('--ignore', default="", help='Comma-separated list of HTML element properties to ignore')
    parser.add_argument('--icons', default="", help='Comma-separated list of HTML element properties to treat as icons')
    parser.add_argument('--show-invisible', action='store_true', help='Show all elements, even if invisible. Mainly useful for simplifying tests by avoiding extra clicks')
    parser.add_argument('filename')
    args = parser.parse_args()
    toIgnore = parseList(args.ignore)
    iconProperties = parseList(args.icons)
    
    text = open(args.filename).read()
    parser = HtmlExtractParser(toIgnore, iconProperties, args.show_invisible)
    print(parser.parse(text))
