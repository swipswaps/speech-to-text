#!/usr/bin/env python
#  -*- coding: utf-8 -*-
import os
import csv
import json
import nltk
import time
import string
import argparse
import numpy as np
import logging
logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
from collections import defaultdict
from speech2text import log_kv, walk_files, get_extension, make_dir
from difflib import SequenceMatcher

"""
What it does:
Compares Google speech-to-text cloud api transcription accuracy vs IBM Watson stt cloud api
over reference documents using Bleu score.

"""

BASE_PATH = "/tmp/stt/AudioJournals/"
GOOGLE_TRANSCRIPTS_PATH = "/tmp/stt/AudioJournals/google_stt"
GOOGLE_TRANSCRIPTS_FILENAME = "transcript.txt"
IBM_TRANSCRIPTS_PATH = "/tmp/stt/AudioJournals/ibm_stt"
IBM_TRANSCRIPTS_FILENAME = "hypotheses.txt"
REFERENCE_TRANSCRIPTS_PATH = "/tmp/stt/AudioJournals/dragon_stt"
STATS_FILEPATH = "/tmp/stt/AudioJournals/text2stats/transcribed_stats.tsv" # generated by etl_transcribe_stats.py
OUTPUT_PATH = "/tmp/stt/AudioJournals/text2stats"
GOOGLE_OUTPUT_FILENAME = "google_v_reference.json"
IBM_OUTPUT_FILENAME = "ibm_v_reference.json"



def load_txt(path):
    result = {}
    log_kv("Loading", path)
    if os.path.exists(path):
        with open(path) as fp:
            result = fp.read()
    else:
        logging.error("Not exist: %s", path)
    return result

def load_stats_tsv(statspath):
    """
    :param statspath: Path to the tsv file that is generated by etl_transcribe_stats.py
    :return: List of keys ordered as appearing in tsv file, and a dictionary containing the tsv data.
    """
    key_list = []
    stats_dict = {}
    header = None
    with open(statspath, 'r') as tsv_fp:
        tsv = csv.reader(tsv_fp, delimiter='\t')
        for row in tsv:
            if not header:
                header = row
                log_kv("header", header)
            else:
                key_list.append(row[0])
                key = row[0]
                if key in stats_dict:
                    logging.error("Key already encountered previously: %s", key)
                    logging.error("Previous entry: %s   New entry: %s", stats_dict[key], row[1:])
                else:
                    stats_dict[key] = {}
                    for ii in range(1,len(header)):
                        stats_dict[key][header[ii]] = row[ii]

    return key_list, stats_dict



def fetch_transcripts(references_folder, transcripts_folder, api="ibm"):
    """
    Determines how many matching reference transcripts there are,
    how many of these were processed,
    and how many succeeded in generating a transcript.
    """
    if api == "ibm":
        transcript_name = "hypotheses.txt"
    elif api == "google":
        transcript_name = GOOGLE_TRANSCRIPTS_FILENAME
    else:
        raise ValueError('Missing api argument')

    comparison_dict = defaultdict(dict)
    for key in key_list:
        folder = os.path.join(references_folder, os.path.dirname(key))
        if os.path.isdir(folder):
            filebase = os.path.splitext(os.path.basename(key))[0]
            reference_filepath = os.path.join(folder, filebase + ".txt")
            if not os.path.exists(reference_filepath):
                reference_filepath = os.path.join(folder, filebase + ".rtf")
                if os.path.exists(reference_filepath):
                    raise ValueError("This file needs to be converted to TXT: %s", reference_filepath)
                else:
                    continue
            comparison_dict[key]["reference_path"] = reference_filepath

            #   Was transcript attempted?
            transcript_folder = os.path.join(transcripts_folder, key + ".out")
            if os.path.isdir(transcript_folder):
                comparison_dict[key]["tried"] = True
            else:
                logging.error("Expected to find folder: %s", transcript_folder)
                continue

            #   Was transcript created?
            transcript_filepath = os.path.join(transcripts_folder, key + ".out", transcript_name)
            if not os.path.exists(transcript_filepath):
                transcript_filepath = os.path.join(transcripts_folder, key + ".out", transcript_name + ".dictated")
                if not os.path.exists(transcript_filepath):
                    comparison_dict[key]["succeeded"] = False
                    continue

            comparison_dict[key]["succeeded"] = True
            comparison_dict[key]["transcript_path"] = transcript_filepath

    return comparison_dict


def ratcliff_obershelp_similarity(a, b):
    """
    A kind of approximate string matching.
    Computes the generalized Ratcliff/Obershelp similarity of two strings
    as the number of matching characters divided by the total number of characters in the two strings.
    Matching characters are those in the longest common subsequence plus,
    recursively matching characters in the unmatched region on either side of the longest common subsequence.
    """
    if a and b:
        return SequenceMatcher(None, a, b).ratio()
    else:
        return None


contractions_fullset = {
    "ain't": "am not; are not; is not; has not; have not",
    "aren't": "are not; am not",
    "can't": "cannot",
    "can't've": "cannot have",
    "'cause": "because",
    "could've": "could have",
    "couldn't": "could not",
    "couldn't've": "could not have",
    "didn't": "did not",
    "doesn't": "does not",
    "don't": "do not",
    "hadn't": "had not",
    "hadn't've": "had not have",
    "hasn't": "has not",
    "haven't": "have not",
    "he'd": "he had / he would",
    "he'd've": "he would have",
    "he'll": "he shall / he will",
    "he'll've": "he shall have / he will have",
    "he's": "he has / he is",
    "how'd": "how did",
    "how'd'y": "how do you",
    "how'll": "how will",
    "how's": "how has / how is / how does",
    "I'd": "I had / I would",
    "I'd've": "I would have",
    "I'll": "I shall / I will",
    "I'll've": "I shall have / I will have",
    "I'm": "I am",
    "I've": "I have",
    "isn't": "is not",
    "it'd": "it had / it would",
    "it'd've": "it would have",
    "it'll": "it shall / it will",
    "it'll've": "it shall have / it will have",
    "it's": "it has / it is",
    "let's": "let us",
    "ma'am": "madam",
    "mayn't": "may not",
    "might've": "might have",
    "mightn't": "might not",
    "mightn't've": "might not have",
    "must've": "must have",
    "mustn't": "must not",
    "mustn't've": "must not have",
    "needn't": "need not",
    "needn't've": "need not have",
    "o'clock": "of the clock",
    "oughtn't": "ought not",
    "oughtn't've": "ought not have",
    "shan't": "shall not",
    "sha'n't": "shall not",
    "shan't've": "shall not have",
    "she'd": "she had / she would",
    "she'd've": "she would have",
    "she'll": "she shall / she will",
    "she'll've": "she shall have / she will have",
    "she's": "she has / she is",
    "should've": "should have",
    "shouldn't": "should not",
    "shouldn't've": "should not have",
    "so've": "so have",
    "so's": "so as / so is",
    "that'd": "that would / that had",
    "that'd've": "that would have",
    "that's": "that has / that is",
    "there'd": "there had / there would",
    "there'd've": "there would have",
    "there's": "there has / there is",
    "they'd": "they had / they would",
    "they'd've": "they would have",
    "they'll": "they shall / they will",
    "they'll've": "they shall have / they will have",
    "they're": "they are",
    "they've": "they have",
    "to've": "to have",
    "wasn't": "was not",
    "we'd": "we had / we would",
    "we'd've": "we would have",
    "we'll": "we will",
    "we'll've": "we will have",
    "we're": "we are",
    "we've": "we have",
    "weren't": "were not",
    "what'll": "what shall / what will",
    "what'll've": "what shall have / what will have",
    "what're": "what are",
    "what's": "what has / what is",
    "what've": "what have",
    "when's": "when has / when is",
    "when've": "when have",
    "where'd": "where did",
    "where's": "where has / where is",
    "where've": "where have",
    "who'll": "who shall / who will",
    "who'll've": "who shall have / who will have",
    "who's": "who has / who is",
    "who've": "who have",
    "why's": "why has / why is",
    "why've": "why have",
    "will've": "will have",
    "won't": "will not",
    "won't've": "will not have",
    "would've": "would have",
    "wouldn't": "would not",
    "wouldn't've": "would not have",
    "y'all": "you all",
    "y'all'd": "you all would",
    "y'all'd've": "you all would have",
    "y'all're": "you all are",
    "y'all've": "you all have",
    "you'd": "you had / you would",
    "you'd've": "you would have",
    "you'll": "you shall / you will",
    "you'll've": "you shall have / you will have",
    "you're": "you are",
    "you've": "you have"
}


contractions = {
    "ain't": "is not",
    "aren't": "are not",
    "can't": "cannot",
    "could've": "could have",
    "couldn't": "could not",
    "didn't": "did not",
    "doesn't": "does not",
    "don't": "do not",
    "hadn't": "had not",
    "hasn't": "has not",
    "haven't": "have not",
    "he'd": "he would",
    "he'll": "he shall / he will",
    "he's": "he has / he is",
    "how'll": "how will",
    "how's": "how is",
    "I'd": "I would",
    "I'll": "I will",
    "I'm": "I am",
    "I've": "I have",
    "isn't": "is not",
    "it'll": "it will",
    "it's": "it is",
    "let's": "let us",
    "ma'am": "madam",
    "must've": "must have",
    "n't": " not",
    "o'clock": "of the clock",
    "she'd": "she had",
    "she'll": "she will",
    "she's": "she is",
    "should've": "should have",
    "so's": "so is",
    "that's": "that is",
    "there's": "there is",
    "they'll": "they will",
    "they're": "they are",
    "they've": "they have",
    "wasn't": "was not",
    "we'd": "we had",
    "we'll": "we will",
    "we're": "we are",
    "we've": "we have",
    "weren't": "were not",
    "what's": "what is",
    "where'd": "where did",
    "where's": "where is",
    "who'll": "who will",
    "who's": "who is",
    "won't": "will not",
    "would've": "would have",
    "wouldn't": "would not",
    "y'all": "you all",
    "you'd": "you would",
    "you'll": "you will",
    "you're": "you are",
    "you've": "you have"
}

def replace_contractions(document):
    """
    Replaces occurences of English language contractions. Should be done before lower()
    :param document:
    :return:
    """
    for x in contractions:
        document = document.replace(x, contractions[x])
    return document

def remove_punctuation(ss):
    return ss.translate(None, string.punctuation)

def replace_special(ss):
    return ss.replace("\t"," ").replace("\n"," ")


tokenizer = nltk.tokenize.RegexpTokenizer(r'\w+')
def tokenize(document):
    """
    :param document: String containing words, punctuation, and newline characters.
    :return: list of strings, with punctuation and newlines removed.
    """
    result = []
    if document:
        result = replace_special(document)
        result = replace_contractions(result)
        result = result.lower()
        result = tokenizer.tokenize(result)
    return result


def jaccard_score(list1, list2):
    return float(len(set(list1).intersection(set(list2)))) / len(set(list1).union(set(list2)))


def do_comparisons(stats, verbose=False):
    """
    Calculates bleu and ratcliff similarity between reference and hypothesis transcripts.
    :param stats: dict containing pointers to reference and hypothesis transcripts.
    :param verbose:
    :return: first argument, supplemented with bleu and ratcliff stats.
    """

    count = 0
    for key in stats:
        if "reference_path" in stats[key] and "transcript_path" in stats[key]:
            if not os.path.exists(stats[key]["reference_path"]) :
                raise ValueError("Expected path to exist: %s", stats[key]["reference_path"])
            if not os.path.exists(stats[key]["transcript_path"]) :
                raise ValueError("Expected path to exist: %s", stats[key]["transcript_path"])
            with open(stats[key]["reference_path"], "r") as fp1:
                reference_string = fp1.read()
            with open(stats[key]["transcript_path"], "r") as fp2:
                hypothesis_string = fp2.read()
            stats[key]["ratcliff"] = ratcliff_obershelp_similarity(reference_string, hypothesis_string)

            reference_tokens = tokenize(reference_string)
            hypothesis_tokens = tokenize(hypothesis_string)
            if len(reference_tokens) < 7 :
                bleu_score = nltk.translate.bleu_score.sentence_bleu(reference_tokens, hypothesis_tokens, weights = (0.5, 0.5))
                if verbose:
                    logging.warn("Short reference: %2d words. Hypothesis:%5d words.  Bleu: %.5f",
                                 len(reference_tokens), len(hypothesis_tokens), bleu_score)
                    if len(hypothesis_tokens) > 2*len(reference_tokens):
                        logging.warn("Reference path : %s", stats[key]["reference_path"])
                        logging.warn("Hypothesis path: %s", stats[key]["transcript_path"])
            elif len(hypothesis_tokens) < 15:
                bleu_score = nltk.translate.bleu_score.sentence_bleu(reference_tokens, hypothesis_tokens,
                                                                     weights=(0.5, 0.5))
                jaccard = jaccard_score(reference_tokens, hypothesis_tokens)
                size_h = len(set(hypothesis_tokens))
                size_r = len(set(reference_tokens))
                size_b = size_h + size_r
                avg_bleu_score = (bleu_score * size_h/size_b) + (jaccard * size_r/size_b)
                if verbose:
                    logging.warn("Short hypothesis. Using avg(bleu,jaccard).  "
                             "Reference:%5d words/%5d set. Hypothesis:%5d words/%5d set. "
                             "Bleu: %.5f  Jaccard: %.5f  Avg: %.5f",
                             len(reference_tokens), size_r, len(hypothesis_tokens), size_h, bleu_score, jaccard, avg_bleu_score)
                if avg_bleu_score > max(bleu_score, jaccard):
                    print
                    logging.error("Avg bleu (%.5f) > max(bleu, jaccard).", avg_bleu_score)
                    logging.warn("avg_bleu_score = (bleu_score * size_h/size_b + (jaccard * size_r/size_b))")
                    logging.warn("       %.5f = ( %.5f * %d/%d ) + ( %.5f * %d/%d )",
                                 avg_bleu_score, bleu_score, size_h, size_b, jaccard, size_r, size_b)
                    print
                bleu_score = avg_bleu_score
            else:
                bleu_score = nltk.translate.bleu_score.sentence_bleu(reference_tokens, hypothesis_tokens)
            stats[key]['bleu'] = bleu_score
            stats[key]['word_count'] = len(reference_tokens)

            count += 1
            if count%50 == 0:
                log_kv("completed", count)
            #
            # if count<11:
            #     break
        else:
            continue

    log_kv("done", count)
    return stats


def calc_bleu_scores(google_results, ibm_results, verbose=False):
    """
    :param google_results: basic stats about google transcripts
    :param ibm_results:  basic stats about ibm transcripts
    :param verbose: prints warnings when bleu is averaged with jaccard,
    which is done when hypothesis word count falls below threshold.
    :return: first two arguments, supplemented with bleu and ratcliff
    """
    logging.info("===   Processing Google transcripts   ===")
    time2 = time.time()
    google_results = do_comparisons(google_results, verbose)
    logging.info("(%.2f min)" % ((time.time() - time2) / 60.0))

    logging.info("===   Processing IBM transcripts   ===")
    time3 = time.time()
    ibm_results = do_comparisons(ibm_results)
    logging.info("(%.2f min)" % ((time.time() - time3) / 60.0))

    ibm_bleu_count = len([1 for x in ibm_results if "bleu" in ibm_results[x]])
    ibm_avg_bleu = sum([ibm_results[x]["bleu"] for x in ibm_results if "bleu" in ibm_results[x]]) \
                   / float(ibm_bleu_count)
    google_bleu_count = len([1 for x in google_results if "bleu" in google_results[x]])
    google_avg_bleu = sum([google_results[x]["bleu"] for x in google_results if "bleu" in google_results[x]]) \
                      / float(google_bleu_count)
    print
    log_kv("ibm bleu count",ibm_bleu_count)
    log_kv("google bleu count", google_bleu_count)
    log_kv("ibm avg bleu", "%.5f" % ibm_avg_bleu)
    log_kv("google avg bleu", "%.5f" % google_avg_bleu)

    ibm_ratcliff_count = len([1 for x in ibm_results if "ratcliff" in ibm_results[x]])
    ibm_avg_ratcliff = sum([ibm_results[x]["ratcliff"] for x in ibm_results if "ratcliff" in ibm_results[x]]) \
                       / float(ibm_ratcliff_count)
    google_ratcliff_count = len([1 for x in google_results if "ratcliff" in google_results[x]])
    google_avg_ratcliff = sum([google_results[x]["ratcliff"] for x in google_results if "ratcliff" in google_results[x]]) \
                          / float(google_ratcliff_count)
    print
    log_kv("ibm ratcliff count",ibm_ratcliff_count)
    log_kv("google ratcliff count", google_ratcliff_count)
    log_kv("ibm avg ratcliff", "%.5f" % ibm_avg_ratcliff)
    log_kv("google avg ratcliff", "%.5f" % google_avg_ratcliff)

    return google_results, ibm_results


TOP_1V3 = 10
def pick_top_1v2(top_picks, x, results1, results2, field="bleu"):
    if results1[x].get(field) and results2[x].get(field) and results2[x][field]>0:
        ratio = results1[x][field] / results2[x][field]
        if not top_picks:
            top_picks.append((x, ratio,))
        elif results1[x][field] / results2[x][field] > top_picks[0][1]:
            top_picks.insert(0, (x, ratio,))
            if len(top_picks) > TOP_1V3:
                top_picks.pop()
    return top_picks

TOP = 5
def pick_top(top_picks, x, results1, stats_dict, field1, field2="bleu"):
    if results1[x].get(field2) and stats_dict[x][field1] > 15:
        value = results1[x][field2]
        if not top_picks:
            top_picks.append((x, value,))
        elif results1[x][field2] > top_picks[0][1]:
            top_picks.insert(0, (x, value,))
            if len(top_picks) > TOP:
                top_picks.pop()
    return top_picks


def print_top(top_picks, google_results, ibm_results, stats_dict, field):
    for x in top_picks:
        print "%-70s  %10.3f  G[%s]: %.5f  IW[%s]: %.5f  G(wc): %4s  IW(wc): %4s  D(wc): %4s" % \
              (x[0], x[1], field, google_results[x[0]].get(field), field, ibm_results[x[0]].get(field),
               stats_dict[x[0]]["google_word_count"], stats_dict[x[0]]["ibm_word_count"], google_results[x[0]].get("word_count"))


def print_paths(top_picks, results, stats_dict, field, field2="google_word_count"):
    for x in top_picks:
        print
        print "%-70s  %10.3f  P[%s]: %.5f  P(wc): %4s  D(wc): %4s" % \
              (x[0], x[1], field, results[x[0]].get(field),
               stats_dict[x[0]][field2], results[x[0]].get("word_count"))
        print "Reference   :   ", results[x[0]]['reference_path']
        print "Hypothesis  :   ", results[x[0]]['transcript_path']


QUANTILE = 10
def print_quantiles(vals):
    logging.info("Deciles for %d values", len(vals))
    dd = 0
    msg = ''
    for x in np.percentile(vals, np.arange(0, 100, QUANTILE)):
        msg += '%s: %.4f ' % (dd, x)
        dd += 1
    msg += 'max: %.4f ' % max(vals)
    logging.info(msg)

def print_quantiles_ints(vals):
    logging.info("Deciles for %d values", len(vals))
    dd = 0
    msg = ''
    for x in np.percentile(vals, np.arange(0, 100, QUANTILE)):
        msg += '%s: %d ' % (dd, x)
        dd += 1
    msg += 'max: %d ' % max(vals)
    logging.info(msg)


def dump_json(google_results, ibm_results):
    filepath = os.path.join(outpath,GOOGLE_OUTPUT_FILENAME)
    logging.info("Writing %s", filepath)
    with open(filepath, 'w') as file:
        json.dump(google_results, file, indent=2)
    filepath = os.path.join(outpath,IBM_OUTPUT_FILENAME)
    logging.info("Writing %s", filepath)
    with open(filepath, 'w') as file:
        json.dump(ibm_results, file, indent=2)


def load_json():
    filepath = os.path.join(outpath,GOOGLE_OUTPUT_FILENAME)
    logging.info("Loading from %s", filepath)
    with open(filepath, 'r') as file:
        google_results = json.load(file)

    filepath = os.path.join(outpath,IBM_OUTPUT_FILENAME)
    logging.info("Loading from %s", filepath)
    with open(filepath, 'r') as file:
        ibm_results = json.load(file)

    return google_results, ibm_results

if __name__ == '__main__':

    start_time = time.time()
    parser = argparse.ArgumentParser(description='Tally audio file specs')
    parser.add_argument('--reference','-r', action='store', default=REFERENCE_TRANSCRIPTS_PATH, help='Folder containing reference transcripts')
    parser.add_argument('--google','-g', action='store', default=GOOGLE_TRANSCRIPTS_PATH, help='Folder containing google transcripts')
    parser.add_argument('--ibm','-i', action='store', default=IBM_TRANSCRIPTS_PATH, help='Folder containing ibm transcripts')
    parser.add_argument('--outfolder','-o', action='store', default='/tmp/stt/AudioJournals/text2stats_dev', help='output directory')
    parser.add_argument('--verbose','-v', action='store_true', help='Spew logs profusely.')
    parser.add_argument('--statspath','-s', action='store', default=STATS_FILEPATH, help='TSV file containing transcription stats ')
    parser.add_argument('--api','-a', action='store', default="ibm", help='API. Default=ibm')
    parser.add_argument('--load','-L', action='store_true', help='Load previously stored results.')
    args = parser.parse_args()

    log_kv("Running", __file__)
    log_kv("From", os.path.dirname(os.path.realpath(__file__)))

    references_path = os.path.realpath(os.path.expanduser(args.reference))
    log_kv("references folder", references_path)

    google_path = os.path.realpath(os.path.expanduser(args.google))
    log_kv("google path", google_path)

    ibm_path = os.path.realpath(os.path.expanduser(args.ibm))
    log_kv("ibm path", ibm_path)

    outpath = os.path.realpath(os.path.expanduser(args.outfolder))
    log_kv("outpath", outpath)

    #   Loads transcript statistics file
    statspath = os.path.realpath(args.statspath)
    key_list, stats_dict = load_stats_tsv(statspath)


    if args.load:
        google_results, ibm_results = load_json()
    else:
        #   Fetches paths of matching transcripts for Google
        google_results = fetch_transcripts(references_path, google_path, api="google")

        #   Fetches paths of matching transcripts for Google
        ibm_results = fetch_transcripts(references_path, ibm_path, api="ibm")

        #   Calculates Bleu and Ratcliff scores
        google_results, ibm_results = calc_bleu_scores(google_results, ibm_results, verbose=False)

        dump_json(google_results, ibm_results)

    print
    google_references_count = len([x for x in google_results if google_results[x].get("reference_path")])
    google_num_tried = len([x for x in google_results if google_results[x].get("tried")])
    google_num_succeeded = len([x for x in google_results if google_results[x].get("succeeded")])
    logging.info("Google Total: %d   Tried: %d   Succeeded: %d", google_references_count, google_num_tried,
                 google_num_succeeded)
    print
    ibm_references_count = len([x for x in ibm_results if ibm_results[x].get("reference_path")])
    ibm_num_tried = len([x for x in ibm_results if ibm_results[x].get("tried")])
    ibm_num_succeeded = len([x for x in ibm_results if ibm_results[x].get("succeeded")])
    logging.info("IBM Total:    %d   Tried: %d   Succeeded: %d", ibm_references_count, ibm_num_tried, ibm_num_succeeded)
    print

    #   Finds best and worst of each
    top_google_bleu = []
    top_google_ratcliff = []
    top_ibm_bleu = []
    top_ibm_ratcliff = []

    top_gvi_bleu = []
    top_gvi_ratcliff = []
    top_ivg_bleu = []
    top_ivg_ratcliff = []

    for x in google_results:
        if x not in ibm_results or "bleu" not in google_results[x] or "bleu" not in ibm_results[x]:
            continue

        if google_results[x]["bleu"]==0 and args.verbose:
            logging.warn("Google bleu == 0: %s", x)

        if ibm_results[x]["bleu"]==0 and args.verbose:
            logging.warn("IBM bleu == 0: %s", x)

        top_google_bleu = pick_top(top_google_bleu, x, google_results, stats_dict, 'google_word_count', "bleu")
        top_google_ratcliff = pick_top(top_google_ratcliff, x, google_results, stats_dict, 'google_word_count', "ratcliff")
        top_ibm_bleu = pick_top(top_ibm_bleu, x, ibm_results, stats_dict, 'ibm_word_count', 'bleu')
        top_ibm_ratcliff = pick_top(top_ibm_ratcliff, x, ibm_results, stats_dict, 'ibm_word_count', "ratcliff")

        if "ratcliff" not in google_results[x] or "ratcliff" not in ibm_results[x]:
            continue

        top_gvi_bleu = pick_top_1v2(top_gvi_bleu, x, google_results, ibm_results, field="bleu")
        top_gvi_ratcliff = pick_top_1v2(top_gvi_ratcliff, x, google_results, ibm_results, field="ratcliff")
        top_ivg_bleu = pick_top_1v2(top_ivg_bleu, x, ibm_results, google_results, field="bleu")
        top_ivg_ratcliff = pick_top_1v2(top_ivg_ratcliff, x, ibm_results, google_results, field="ratcliff")


    print "=============================="
    print "       Top Google Bleu"
    print "=============================="
    print_top(top_google_bleu, google_results, ibm_results, stats_dict, "bleu")
    print "=============================="
    print "     Top Google Ratcliff"
    print "=============================="
    print_top(top_google_ratcliff, google_results, ibm_results, stats_dict, "ratcliff")
    print
    print "=============================="
    print "        Top IBM Bleu"
    print "=============================="
    print_top(top_ibm_bleu, google_results, ibm_results, stats_dict, "bleu")
    print "=============================="
    print "      Top IBM Ratcliff"
    print "=============================="
    print_top(top_ibm_ratcliff, google_results, ibm_results, stats_dict, "ratcliff")
    print
    print
    print "=============================="
    print "       Top G / I Bleu"
    print "=============================="
    print_top(top_gvi_bleu, google_results, ibm_results, stats_dict, "bleu")
    print "=============================="
    print "      Top G / I Ratcliff"
    print "=============================="
    print_top(top_gvi_ratcliff, google_results, ibm_results, stats_dict, "ratcliff")
    print
    print
    print "=============================="
    print "       Top I / G Bleu"
    print "=============================="
    print_top(top_ivg_bleu, google_results, ibm_results, stats_dict, "bleu")
    print "=============================="
    print "     Top I / G Ratcliff"
    print "=============================="
    print_top(top_ivg_ratcliff, google_results, ibm_results, stats_dict, "ratcliff")


    print "=============================="
    print "   PATHS for Top I / G Bleu"
    print "=============================="
    print_paths(top_ivg_bleu, google_results, stats_dict, "bleu", "google_word_count")

    print "=============================="
    print " PATHS for Top I / G Ratcliff"
    print "=============================="
    print_paths(top_ivg_ratcliff, google_results, stats_dict, "ratcliff", "google_word_count")

    print "=============================="
    print "           Deciles "
    print "=============================="
    print "===      Google Bleu       ==="
    print "=============================="
    vals = [x["bleu"] for x in google_results.values() if "bleu" in x]
    print_quantiles(vals)

    print "=============================="
    print "===      IBM Bleu       ==="
    print "=============================="
    vals = [x["bleu"] for x in ibm_results.values() if "bleu" in x]
    print_quantiles(vals)
    print "=============================="
    print "===    Google Ratcliff     ==="
    print "=============================="
    vals = [x["ratcliff"] for x in google_results.values() if "ratcliff" in x]
    print_quantiles(vals)
    print "=============================="
    print "===    IBM Ratcliff     ==="
    print "=============================="
    vals = [x["ratcliff"] for x in ibm_results.values() if "ratcliff" in x]
    print_quantiles(vals)

    print "=============================="
    print "     Word Count Deciles "
    print "=============================="
    print "===        Google          ==="
    print "=============================="
    vals = [float(x["google_word_count"]) for x in stats_dict.values() if "google_word_count" in x and x["google_word_count"]]
    print_quantiles_ints(vals)

    print "=============================="
    print "===          IBM           ==="
    print "=============================="
    vals = [float(x["ibm_word_count"]) for x in stats_dict.values() if "ibm_word_count" in x and x["ibm_word_count"]]
    print_quantiles_ints(vals)


    print "=============================="
    print "     Total Word Counts "
    print "=============================="
    count_google = len([int(x["google_word_count"]) for x in stats_dict.values() if "google_word_count" in x and x["google_word_count"]])
    count_ibm = len([int(x["ibm_word_count"]) for x in stats_dict.values() if "ibm_word_count" in x and x["ibm_word_count"]])
    total_google = sum([int(x["google_word_count"]) for x in stats_dict.values() if "google_word_count" in x and x["google_word_count"]])
    total_ibm = sum([int(x["ibm_word_count"]) for x in stats_dict.values() if "ibm_word_count" in x and x["ibm_word_count"]])
    logging.info("%s", "Google: {:,} (out of {:,} transcripts)   IBM: {:,} (out of {:,} transcripts)".format(
                total_google, count_google, total_ibm, count_ibm))

    print "=============================="
    print "     Total Document Counts "
    print "=============================="
    logging.info("Number of audio files:             %d", len(stats_dict))
    logging.info("Number of google transcripts:      %d", len([x for x in stats_dict.values() if "google_word_count" in x and x["google_word_count"]]))
    logging.info("Number of ibm transcripts:         %d", len([x for x in stats_dict.values() if "ibm_word_count" in x and x["ibm_word_count"]]))
    logging.info("Number of ibm transcript attempts: %d", len([x for x in stats_dict.values() if 'ibm_transcribe_seconds' in x  and x['ibm_transcribe_seconds']]))


    logging.info("")
    logging.info("(%.2f min)" % ((time.time() - start_time) / 60.0))
    logging.info("Done: %s", __file__)

