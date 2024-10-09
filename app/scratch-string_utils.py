from typing import Optional
import textwrap

def join_list(joining_list: Optional[list], join_txt: str = "\n") -> str:
    """
    Utility to join a list.

    Functionally equivalent to:
    "" if joining_list is None else "\n".join(joining_list)
    """
    if not joining_list:
        return ""

    return join_txt.join(joining_list)


def basic_ascii(text: str) -> str:
    # See https://www.ascii-code.com/
    return "".join([c if 32 <= ord(c) <= 126 else " " for c in text])


import re
alphabets= "([A-Za-z])"
prefixes = "(Mr|St|Mrs|Ms|Dr)[.]"
suffixes = "(Inc|Ltd|Jr|Sr|Co)"
starters = "(Mr|Mrs|Ms|Dr|Prof|Capt|Cpt|Lt|He\s|She\s|It\s|They\s|Their\s|Our\s|We\s|But\s|However\s|That\s|This\s|Wherever)"
acronyms = "([A-Z][.][A-Z][.](?:[A-Z][.])?)"
websites = "[.](com|net|org|io|gov|edu|me)"
digits = "([0-9])"
multiple_dots = r'\.{2,}'

# Copied from https://stackoverflow.com/questions/4576077/how-can-i-split-a-text-into-sentences
def split_into_sentences(text: str) -> list[str]:
    """
    Split the text into sentences.

    If the text contains substrings "<prd>" or "<stop>", they would lead 
    to incorrect splitting because they are used as markers for splitting.

    :param text: text to be split into sentences
    :type text: str

    :return: list of sentences
    :rtype: list[str]
    """
    text = " " + text + "  "
    text = text.replace("\n"," ")
    text = re.sub(prefixes,"\\1<prd>",text)
    text = re.sub(websites,"<prd>\\1",text)
    text = re.sub(digits + "[.]" + digits,"\\1<prd>\\2",text)
    text = re.sub(multiple_dots, lambda match: "<prd>" * len(match.group(0)) + "<stop>", text)
    if "Ph.D" in text: text = text.replace("Ph.D.","Ph<prd>D<prd>")
    text = re.sub("\s" + alphabets + "[.] "," \\1<prd> ",text)
    text = re.sub(acronyms+" "+starters,"\\1<stop> \\2",text)
    text = re.sub(alphabets + "[.]" + alphabets + "[.]" + alphabets + "[.]","\\1<prd>\\2<prd>\\3<prd>",text)
    text = re.sub(alphabets + "[.]" + alphabets + "[.]","\\1<prd>\\2<prd>",text)
    text = re.sub(" "+suffixes+"[.] "+starters," \\1<stop> \\2",text)
    text = re.sub(" "+suffixes+"[.]"," \\1<prd>",text)
    text = re.sub(" " + alphabets + "[.]"," \\1<prd>",text)
    if "”" in text: text = text.replace(".”","”.")
    if "\"" in text: text = text.replace(".\"","\".")
    if "!" in text: text = text.replace("!\"","\"!")
    if "?" in text: text = text.replace("?\"","\"?")
    text = text.replace(".",".<stop>")
    text = text.replace("?","?<stop>")
    text = text.replace("!","!<stop>")
    text = text.replace("<prd>",".")
    sentences = text.split("<stop>")
    sentences = [s.strip() for s in sentences]
    if sentences and not sentences[-1]: sentences = sentences[:-1]
    return sentences



from pprint import pprint
import random
import nltk
from nltk.tokenize import sent_tokenize
import spacy
if __name__ == "__main__":
    sentences = [f"Sentence {i}:{' word' * 15} last. " for i in range(20)]
    tricky_sentences = [
        "Mr. John Johnson Jr. was born in the U.S.A. but earned his Ph.D. with GPA 3.8 in Israel before joining Nike Inc. as an engineer. What do you think? He also worked at craigslist.org as a business analyst level 2.0. He sounds great!",
        'Some sentence. Mr. Holmes...This is a new sentence!And This is another one.. ',
        'The U.S. Drug Enforcement Administration (DEA) says hello. And have a nice day.',
    ]
    rand_ints = sorted([random.randint(0, len(sentences)) for _ in range(len(tricky_sentences))])
    long_paragraph = ""
    for i, (rand_int, tricky_sentence) in enumerate(zip(rand_ints, tricky_sentences)):
        next_int = rand_ints[i+1] if i+1 < len(rand_ints) else len(sentences)
        long_paragraph += "".join(sentences[:rand_int]) + " " + tricky_sentence + " " + "".join(sentences[rand_int:next_int])
    # print(long_paragraph)

    # lines = textwrap.wrap(long_paragraph, width=180, break_long_words=False, break_on_hyphens=False, replace_whitespace=False)
    lines = split_into_sentences(long_paragraph)

    # nltk.download('punkt_tab')
    # lines = sent_tokenize(long_paragraph)
        
    if False:
        for line in lines:
            print("> ", line)


    if False:
        nlp = spacy.load('en_core_web_sm')
        doc3 = nlp(u'"Management is doing things right; leadership is doing the right things." -Peter Drucker')
        for sent in doc3.sents:
            print(sent)
    def spacy_split_into_phrases(long_sentence: str):
        # cmdline: spacy download en_core_web_sm
        nlp = spacy.load('en_core_web_sm')
        @spacy.Language.component('custom_sent_end_pt')
        def set_custom_Sentence_end_points(doc):
            for token in doc[:-1]:
                if token.text in [';',',','--',]:
                    doc[token.i+1].is_sent_start = True
            return doc    
        nlp.add_pipe('custom_sent_end_pt', before='parser')
        print(nlp.pipe_names)
        #Re-run the Doc object creation:
        # doc4 = nlp(u'"Management is doing things right; leadership is doing the right things." -Peter Drucker')
        doc4 = nlp(long_sentence)
        for sent in doc4.sents:
            print("S> ", sent)
        return [s.text for s in doc4.sents]


    def join_up_to(lines, max_char_length = 212, delimiter = " "):
        chunks = []
        chunk = ""
        for line in lines:
            new_chunk = chunk + delimiter + line
            if len(new_chunk) > max_char_length:
                if chunk:
                    chunks.append(chunk)
                if len(line) < max_char_length:
                    chunk = line
                else:
                    print("WARNING: Sentence too long to fit in a single chunk: ", line)
                    # split on phrases
                    # words = re.split(r'([,;\-\\(\\)])', line)
                    words = spacy_split_into_phrases(line)
                    for word in words:
                        print("]] ", len(word), "\t", word)
                    
                    chunks += join_up_to(words, max_char_length=max_char_length, delimiter="")
                    chunk = ""
            else:
                chunk = new_chunk
        if chunk:
            chunks.append(chunk)
        return chunks

    long_sentence = "Mr. John Johnson Jr. was born in the U.S.A., but earned his Ph.D. (with GPA 3.8) in Israel before joining Nike Inc -- as an engineer; What do you think- He also worked at craigslist.org (as a business analyst level 2.0) He sounds great!"
    chunks = join_up_to([long_sentence], max_char_length=81)

    for chunk in chunks:
        print("] ", len(chunk), chunk)


    if not True:
        for chunk in join_up_to(lines):
            print("} ", len(chunk), chunk)
        
    if not True:
        list_items = [f"- Item {i}:{' word' * 150} last" for i in range(20)]
        # TODO: nest list items
        long_list = "This is an introduction to the list:\n" + "\n".join(list_items)
        print(long_list)

        lines = long_list.split("\n")
        for line in lines:
            print("> ", line)

        intro_text = lines[0]
        print(len(intro_text))
        for chunk in join_up_to(lines[1:], max_char_length=212-len(intro_text)):
            print("} ", len(chunk), chunk)
