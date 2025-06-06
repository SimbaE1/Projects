#!/usr/bin/env python3
"""
auto_sub_solver.py  (v5 – English‑only, adaptive)

Enhancements in this version
----------------------------
• If first simulated‑annealing pass yields a low sense‑ratio (< 80 %), the solver
  automatically **escalates** – triples restarts & iterations and runs a second
  search.
• Fast **Caesar‑shift detector**: tries all 26 rotations first; if a shift gives
  ≥ 80 % common‑word ratio it is returned instantly.
• More robust scoring: bigram+trigram+quadgram blend for noisy or short texts.
• --stop-sense <ratio> lets you set the early‑exit sense threshold

Core features retained: wordfreq Zipf scoring, Jakobsen polish, parallel
restarts, auto‑scaling parameters, optional cleaning, English‑only.

Dependencies
------------
    python -m pip install wordfreq

Usage
-----
    python auto_sub_solver.py --clean [--llama-always] "Ciphertext here …"
"""

from __future__ import annotations
import argparse, math, random, re, string, sys, urllib.request, multiprocessing as mp
import time
import json
from collections import defaultdict
from pathlib import Path
from typing import Tuple

# ----------------------------------------------------------------------
# Global to hold CLI args for llama verbose
# ----------------------------------------------------------------------
args_global = None  # will be set in main()

# ----------------------------------------------------------------------
# requests import (optional for llama check)
# ----------------------------------------------------------------------
try:
    import requests
except ImportError:
    requests = None

# ----------------------------------------------------------------------
# 0.  Constants & basic helpers
# ----------------------------------------------------------------------
ALPHA = string.ascii_uppercase
LETTER_SPACE = set(ALPHA + " ")
IGNORE_SET: set[str] = set()   # words the sense‑ratio should skip
CACHE_DIR = Path(__file__).with_name(Path(__file__).stem + "_data")
CACHE_DIR.mkdir(exist_ok=True)
QUAD_FILE = CACHE_DIR / "english_quadgrams.txt"
TRI_FILE  = CACHE_DIR / "english_trigrams.txt"
BI_FILE   = CACHE_DIR / "english_bigrams.txt"

MIRRORS = {
    QUAD_FILE: [
        "https://raw.githubusercontent.com/torognes/enigma/master/english_quadgrams.txt",
        "http://practicalcryptography.com/media/cryptanalysis/files/english_quadgrams.txt",
    ],
    TRI_FILE: [
        "https://raw.githubusercontent.com/napsternxg/ciphers/master/resources/english_trigrams.txt",
    ],
    BI_FILE: [
        "https://raw.githubusercontent.com/napsternxg/ciphers/master/resources/english_bigrams.txt",
    ],
}

# ----------------------------------------------------------------------
# 1.  Download / load n‑gram tables
# ----------------------------------------------------------------------

def _download(urls: list[str], dest: Path):
    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                dest.write_bytes(r.read())
            print(f"[+] cached {dest.name} from {url}")
            return
        except Exception as e:
            print(f"[-] {url}: {e}")
    sys.exit(f"Failed to fetch {dest.name}; add it manually.")

def _load_ngrams(path: Path, order: int) -> dict[str,float]:
    if not path.exists():
        _download(MIRRORS[path], path)
    total, counts = 0, {}
    with path.open() as fh:
        for line in fh:
            parts = line.split()
            gram = parts[0].upper()
            cnt  = int(parts[1]) if len(parts) > 1 else int(parts[0])  # some lists omit counts
            if len(gram) == order:
                counts[gram] = cnt
                total += cnt
    return {g: math.log10(c / total) for g, c in counts.items()}

QUAD_P = _load_ngrams(QUAD_FILE, 4)
TRI_P  = _load_ngrams(TRI_FILE, 3)
BI_P   = _load_ngrams(BI_FILE, 2)
FLOOR4 = math.log10(0.01 / sum(10 ** p for p in QUAD_P.values()))
FLOOR3 = math.log10(0.01 / sum(10 ** p for p in TRI_P.values()))
FLOOR2 = math.log10(0.01 / sum(10 ** p for p in BI_P.values()))


def ngram_score(text: str) -> float:
    text = re.sub("[^A-Z]", "", text)
    s4 = sum(QUAD_P.get(text[i:i+4], FLOOR4) for i in range(len(text)-3))
    s3 = sum(TRI_P.get(text[i:i+3], FLOOR3)  for i in range(len(text)-2))
    s2 = sum(BI_P.get(text[i:i+2], FLOOR2)   for i in range(len(text)-1))
    # weighting: quad 1.0, tri 0.3, bi 0.1
    return s4 + 0.3*s3 + 0.1*s2

# ----------------------------------------------------------------------
# 2.  Wordfreq scoring & sense metric
# ----------------------------------------------------------------------
try:
    from wordfreq import zipf_frequency
except ImportError:
    sys.exit("wordfreq missing – install: pip install wordfreq")

def word_score(text: str) -> float:
    return sum(zipf_frequency(w.lower(), "en") for w in re.findall(r"[A-Z]{2,}", text))

def sense_ratio(text: str, thr: float = 3.5) -> float:
    """Return fraction of tokens with Zipf ≥ thr, ignoring names in IGNORE_SET."""
    words = [w for w in re.findall(r"[A-Z]{1,}", text)
             if w.lower() not in IGNORE_SET]
    if not words:
        return 1.0   # nothing left to score ⇒ treat as perfect
    good = sum(zipf_frequency(w.lower(), "en") >= thr for w in words)
    return good / len(words)

# ----------------------------------------------------------------------
# 3.  Utility functions
# ----------------------------------------------------------------------

def clean(t: str) -> str:
    return "".join(ch for ch in t.upper() if ch in LETTER_SPACE)

def random_key() -> str:
    return "".join(random.sample(ALPHA, 26))

def swap_two(k: str) -> str:
    a,b = random.sample(range(26),2)
    lst=list(k); lst[a],lst[b]=lst[b],lst[a]
    return "".join(lst)

def decode(ct: str, key: str) -> str:
    return ct.upper().translate(str.maketrans(ALPHA, key))

# ----------------------------------------------------------------------
# Llama-3 coherence check helper
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# Llama-3 coherence check helper
# ----------------------------------------------------------------------
def llama_is_english(text: str, url: str, timeout: int = 15) -> bool:
    """
    Ask a local Llama‑3/Ollama server whether the text is coherent English.
    Returns True on a confident 'yes', False otherwise.
    """
    # Early exit if requests isn't available
    if requests is None:
        if getattr(args_global, "llama_verbose", False):
            print("[!] 'requests' module not found – skipping Llama‑check. "
                  "Install it with:  pip install requests")
        return False
    prompt = (
        "Answer only YES or NO.\n\n"
        "You are an expert cryptanalyst. The text below is the tentative "
        "plaintext recovered from a newspaper Cryptoquip (simple mono‑alphabetic "
        "substitution cipher). If it reads as coherent, grammatical English prose "
        "or verse, answer YES. Otherwise answer NO.\n"
        "-----\n"
        f"{text[:1200]}\n"
        "-----\n"
    )

    try:
        resp = requests.post(url,
                             json={"model": "llama3", "prompt": prompt},
                             timeout=timeout)
        if resp.status_code == 200:
            if getattr(args_global, "llama_verbose", False):
                print(f"[Llama‑check] raw response: {resp.text[:200]!r}")
            if 'yes' in resp.text.lower():
                return True
    except Exception as e:
        if getattr(args_global, "llama_verbose", False):
            print(f"[Llama‑check] call failed: {e}")
    return False

# ----------------------------------------------------------------------
# If Llama‑3 says the text is *not* fluent, ask it to suggest a fix
# ----------------------------------------------------------------------
def llama_suggest_fix(text: str, url: str, timeout: int = 30) -> str | None:
    """
    Ask Llama‑3 to rewrite / repair the supplied text.
    Returns the suggested rewrite (string) or None on failure.
    """
    if requests is None:
        return None
    prompt = (
        "The text below is supposed to be the plaintext of a Cryptoquip "
        "(alphabet‑substitution cipher) but still looks garbled. "
        "Please rewrite it as coherent English (or show what it was meant to say). "
        "Return only the improved text.\n"
        "-----\n"
        f"{text[:2000]}\n"
        "-----\n"
    )
    try:
        resp = requests.post(
            url,
            json={"model": "llama3", "prompt": prompt},
            timeout=timeout,
            stream=True,           # enable streaming
        )
        if resp.status_code == 200:
            chunks: list[str] = []
            # Ollama returns one JSON object per line; collect "response" fields
            for line in resp.iter_lines(decode_unicode=True):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    chunks.append(obj.get("response", ""))
                except Exception:
                    # ignore malformed fragments
                    continue
            suggestion = "".join(chunks).strip()
            suggestion = suggestion.replace("\n", " ").strip()
            if suggestion:
                return suggestion
    except Exception:
        pass
    return None

# ----------------------------------------------------------------------
# Helper: pretty‑print Llama suggestions
# ----------------------------------------------------------------------
def _fmt_llama_suggestion(text: str) -> str:
    """Return a neatly wrapped block with a header for Llama rewrites."""
    import textwrap
    header = "\n[Llama‑suggest] possible rewrite ↓\n" + ("-" * 60)
    wrapped = textwrap.fill(text.strip(), width=78)
    return f"{header}\n{wrapped}\n"

# ----------------------------------------------------------------------
# 4.  Caesar shift quick check
# ----------------------------------------------------------------------

def caesar_try(ct: str, use_clean: bool) -> Tuple[str|None,str|None,float]:
    best_ratio, best_plain, best_key = 0.0, None, None
    for s in range(26):
        tbl = str.maketrans(ALPHA, ALPHA[s:]+ALPHA[:s])
        plain = ct.upper().translate(tbl)
        txt = clean(plain) if use_clean else plain.upper()
        r = sense_ratio(txt)
        if r>best_ratio:
            best_ratio, best_plain, best_key = r, plain, tbl
    if best_ratio>=0.90:
        return best_plain, "CAESAR", best_ratio
    return None, None, best_ratio

# ----------------------------------------------------------------------
# 5.  Jakobsen polish
# ----------------------------------------------------------------------

def jakobsen(key:str,cipher:str,lam:float,use_clean:bool)->Tuple[str,float]:
    best_key,changed=key,True
    while changed:
        changed=False
        for i in range(25):
            for j in range(i+1,26):
                lst=list(best_key);lst[i],lst[j]=lst[j],lst[i]
                k2="".join(lst)
                raw=decode(cipher,k2)
                txt=clean(raw) if use_clean else raw.upper()
                s=ngram_score(txt)+lam*word_score(txt)
                raw0=decode(cipher,best_key)
                txt0=clean(raw0) if use_clean else raw0.upper()
                s0=ngram_score(txt0)+lam*word_score(txt0)
                if s>s0:
                    best_key=k2;changed=True
    final_s=ngram_score(clean(decode(cipher,best_key)))+lam*word_score(clean(decode(cipher,best_key)))
    return best_key,final_s

# ----------------------------------------------------------------------
# 6.  Annealing worker
# ----------------------------------------------------------------------

def _worker(args):
    cipher,restarts,iters,lam,clean_flag,seed=args
    start_time = time.time()
    print(f"[worker {seed}] starting – {restarts} restarts total")
    random.seed(seed)
    best_s,bk,br=float('-inf'),None,''
    for idx in range(restarts):
        key=random_key(); raw=decode(cipher,key)
        txt=clean(raw) if clean_flag else raw.upper()
        s=ngram_score(txt)+lam*word_score(txt); temp=20.0
        for _ in range(iters):
            k2=swap_two(key); r2=decode(cipher,k2)
            t2=clean(r2) if clean_flag else r2.upper()
            s2=ngram_score(t2)+lam*word_score(t2)
            d=s2-s
            if d>0 or math.exp(d/temp)>random.random():
                key,raw,txt,s=k2,r2,t2,s2
            temp*=0.995
        if s>best_s:
            bk,br,best_s=key,raw,s
        if idx % max(1, restarts // 50) == 0:  # update ~2% steps
            pct = (idx / restarts) * 100
            elapsed = time.time() - start_time
            print(f"[worker {seed}] {pct:5.1f}%  "
                  f"best={best_s:.1f}  elapsed={elapsed:4.1f}s",
                  end="\r", flush=True)
    total_time = time.time() - start_time
    print(f"[worker {seed}] finished – best score {best_s:.2f} "
          f"in {total_time:.1f}s".ljust(80))
    return bk,br,best_s

# ----------------------------------------------------------------------
# 7.  Crack orchestrator with adaptive escalation
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# 7‑a.  Single‑pass crack (used by adaptive loop)
# ----------------------------------------------------------------------
def crack_once(cipher: str,
               restarts: int,
               iters: int,
               lam: float,
               use_clean: bool,
               parallel: bool) -> Tuple[str, str, float]:
    """
    One simulated‑annealing run (with parallel restarts) + Jakobsen polish.
    Returned tuple: (best_key, best_plaintext, combined_score).
    """
    ncpu = mp.cpu_count() if parallel else 1
    chunk = (restarts + ncpu - 1) // ncpu
    tasks = [(cipher, chunk, iters, lam, use_clean,
              random.randrange(1 << 30)) for _ in range(ncpu)]
    if parallel and ncpu > 1:
        with mp.Pool(ncpu) as pool:
            results = pool.map(_worker, tasks)
    else:
        results = [_worker(t) for t in tasks]

    key, raw, score = max(results, key=lambda x: x[2])
    key, score = jakobsen(key, cipher, lam, use_clean)
    raw = decode(cipher, key)
    return key, raw, score

def crack(cipher: str,
          restarts: int,
          iters: int,
          lam: float,
          use_clean: bool,
          parallel: bool,
          stop_sense: float,
          args) -> Tuple[str, str, float]:
    # First try Caesar
    caesar_plain, caesar_key, ratio = caesar_try(cipher, use_clean)
    if caesar_plain:
        return caesar_key, caesar_plain, ratio

    key, raw, score = crack_once(cipher, restarts, iters, lam,
                                 use_clean, parallel)
    # Compute actual ratio immediately after first pass
    ratio = sense_ratio(clean(raw) if use_clean else raw.upper())
    # show first attempt immediately
    print("\n[ preview after first pass ]\n" + raw[:600] +
          (" …\n" if len(raw) > 600 else "\n"))
    # Optional Llama‑3 sanity check
    llama_ok = False
    if args.llama_check and (getattr(args, "llama_always", False) or ratio >= stop_sense * 0.75):
        llama_ok = llama_is_english(raw, args.llama_url)
        if llama_ok:
            print("[*] Llama‑3 confirms the text is coherent English.")
        else:
            # Llama responded "NO" – try to get a best‑guess rewrite
            suggestion = llama_suggest_fix(raw, args.llama_url)
            if suggestion:
                print(_fmt_llama_suggestion(suggestion))

    # ---- Ask user whether to accept, improve, or abandon before escalation ----
    if llama_ok or ratio >= stop_sense:
        try:
            ans = input(
                "Accept this decryption or keep searching for a potentially better one? "
                "[A]ccept / [S]earch / [Q]uit  "
            ).strip().lower()
        except EOFError:
            ans = "a"          # default to accept if input stream closed

        if ans.startswith("s"):        # user wants more searching
            # fall‑through to escalation loop below
            pass
        elif ans.startswith("q"):
            sys.exit(0)
        else:                          # accept by default
            return key, raw, ratio
    if ratio < stop_sense and not llama_ok:
        try:
            ans = input("Does that look correctly decrypted so far? [Y/n] ").strip().lower()
        except EOFError:
            ans = "n"
        if ans in ("y", ""):
            return key, raw, ratio
    best_key, best_raw, best_ratio = key, raw, ratio
    rounds = 0
    while ratio < stop_sense and rounds < 3:
        print(f"[!] Sense {ratio:.0%} – escalating search (round {rounds+1}) …")
        rounds += 1
        restarts *= 3
        iters    *= 3
        lam      *= 1.1                         # favour dictionary words
        key, raw, _ = crack_once(cipher, restarts, iters, lam,
                                 use_clean, parallel)
        ratio = sense_ratio(clean(raw) if use_clean else raw.upper())
        if ratio > best_ratio:
            best_key, best_raw, best_ratio = key, raw, ratio
            print(f"\n[ preview round {rounds} ]\n" +
                  best_raw[:600] + (" …\n" if len(best_raw) > 600 else "\n"))

    if best_ratio < stop_sense:
        print(f"[!] Gave up after {rounds} escalations – best sense "
              f"{best_ratio:.0%}. Returning best attempt.\n")

    return best_key, best_raw, best_ratio

# ----------------------------------------------------------------------
# 8.  Auto scale params
# ----------------------------------------------------------------------

def autoscale(n:int)->Tuple[int,int]:
    return max(60,n//3),max(5000,n*30)

# ----------------------------------------------------------------------
# 9.  CLI
# ----------------------------------------------------------------------

def main():
    ap=argparse.ArgumentParser(description="Adaptive English substitution‑cipher solver")
    ap.add_argument('cipher',nargs='*',help='Ciphertext (or stdin)')
    ap.add_argument('--clean',action='store_true',help='Strip non‑letters for scoring')
    ap.add_argument('--lambda',dest='lam',type=float,default=1.5)
    ap.add_argument('-r','--restarts',type=int,help='Random restarts')
    ap.add_argument('-i','--iters',type=int,help='Iterations per restart')
    ap.add_argument('--no-parallel',action='store_true')
    ap.add_argument('--file', metavar='PATH', help='Read ciphertext from file')
    ap.add_argument('--ignore', action='append', default=[],
                    help='Word(s) the sense metric should ignore; '
                         'use multiple --ignore flags or comma‑separate')
    ap.add_argument('--stop-sense', type=float, default=0.80,
                    metavar='RATIO',
                    help='Sense‑ratio at which to stop (default 0.80)')
    ap.add_argument('--llama-check', action='store_true',
                    help='Ping a local Llama‑3/Ollama endpoint to confirm '
                         'whether the decrypted text is coherent English')
    ap.add_argument('--llama-url', default='http://localhost:11434/api/generate',
                    metavar='URL',
                    help='URL of the Ollama /generate endpoint '
                         '(default: %(default)s)')
    ap.add_argument('--llama-verbose', action='store_true',
                    help='Print the raw response text returned by the '
                         'Ollama /generate endpoint')
    ap.add_argument('--llama-always', action='store_true',
                    help='Query Llama even when sense‑ratio is below the threshold')
    args=ap.parse_args()

    # Make CLI flags available to helper functions early
    global args_global
    args_global = args

    # Diagnostic: warn if llama_check requested but requests missing
    if args.llama_check and requests is None:
        print("[!] '--llama-check' requested but the 'requests' library is missing. "
              "Run:  pip install requests  (or disable the flag).")

    # populate IGNORE_SET
    for item in args.ignore:
        for w in item.split(','):
            w = w.strip().lower()
            if w:
                IGNORE_SET.add(w)
    if IGNORE_SET:
        print(f"[*] Ignoring {', '.join(sorted(IGNORE_SET))} in sense metric")

    if args.file:
        cipher_raw = Path(args.file).read_text(encoding="utf-8").strip()
    elif args.cipher:
        cipher_raw = " ".join(args.cipher)
    else:
        print("Paste ciphertext.  Finish with Ctrl‑D (mac/Linux) or Ctrl‑Z then Enter (Windows):")
        cipher_raw = sys.stdin.read().strip()
    r,i=(args.restarts,args.iters)
    if r is None or i is None:
        r_auto,i_auto=autoscale(len(cipher_raw)); r=r or r_auto; i=i or i_auto
        print(f"[*] Auto params  restarts={r}  iterations={i}")

    key, plain, score = crack(cipher_raw, r, i, args.lam,
                              args.clean, not args.no_parallel,
                              args.stop_sense, args)
    print(f"\n[+] Best key  : {key}")
    sr=sense_ratio(clean(plain) if args.clean else plain.upper())
    print(f"[+] Sense‑ratio: {sr:.2%}\n\n===== Decryption =====\n")
    print(plain)


if __name__=='__main__':
    main()