import re
from pathlib import Path

def fix_layer1(text):
    text=re.sub(r'\(cid:\d+\)','•',text)
    # rejoin hyphen-split words:  "aggre-\ngation" → "aggregation"
    text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)
    return text

def fix_layer2(text):
    text = re.sub(r'^[-=\*]{3,}\s*$','',text,flags=re.MULTILINE)
    # spaces around punctuation  "8 . 6" → "8.6",  "50 %" → "50%"
    text = re.sub(r'(\d)\s+\.\s+(\d)', r'\1.\2', text)
    text = re.sub(r'\s+\.','.',text) # for multiple spaces before a period it is always invalid
    text = re.sub(r'(\d)\s+%', r'\1%', text)
    text = re.sub(r'\s+,', ',', text)
    text = re.sub(r'\s+:', ':', text)
    # collapse 3+spaces to one
    text = re.sub(r'\s{3,}',' ',text)
    # collapse 3+ blank lines to one
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# problem is if content got merged with section name
# then we can have diff formattings like upper case two worded sec
# or capitalized sections
import re

KNOWN_SECTIONS = {
    "education",
    "experience",
    "skills",
    "projects",
    "personal projects",
    "technical skills"
}


def fix_sections(full_text):

    # split whole resume text into lines
    lines = full_text.splitlines()

    fixed = []

    # longest sections checked first
    sections = sorted(KNOWN_SECTIONS, key=len, reverse=True)

    for line in lines:

        line = line.strip()

        matched = False

        for sec in sections:

            # pattern explanation:
            #
            # ^                       -> start of line
            # re.escape(sec)          -> safely match section name
            # \s*                     -> any number of spaces
            # [:*\-]*                 -> optional :, *, -
            # \s*                     -> spaces again
            # (.+)?                   -> remaining content after section
            #
            pattern = rf"^{re.escape(sec)}\s*[:*\-]*\s*(.+)?$"

            match = re.match(pattern, line, re.IGNORECASE)

            if match:

                content = match.group(1)

                # add clean section heading
                fixed.append(sec.upper())

                # if content exists after heading
                if content:
                    fixed.append(content.strip())

                matched = True
                break

        if not matched:
            fixed.append(line)

    return "\n".join(fixed)