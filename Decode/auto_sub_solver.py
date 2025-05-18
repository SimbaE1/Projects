#!/usr/bin/env python3
"""
auto_sub_solver.py  (v5 – English‑only, adaptive)

Enhancements in this version
----------------------------
• If first simulated‑annealing pass yields a low sense‑ratio (< 90 %), the solver
  automatically **escalates** – triples restarts & iterations and runs a second
  search.
• Fast **Caesar‑shift detector**: tries all 26 rotations first; if a shift gives
  ≥ 90 % common‑word ratio it is returned instantly.
• More robust scoring: bigram+trigram+quadgram blend for noisy or short texts.

Core features retained: wordfreq Zipf scoring, Jakobsen polish, parallel
restarts, auto‑scaling parameters, optional cleaning, English‑only.

Dependencies
------------
    python -m pip install wordfreq

Usage
-----
    python auto_sub_solver.py --clean "Ciphertext here …"
"""
from __future__ import annotations
import argparse, math, random, re, string, sys, urllib.request, multiprocessing as mp
import time
from collections import defaultdict
from pathlib import Path
from typing import Tuple

# ----------------------------------------------------------------------
# 0.  Constants & basic helpers
# ----------------------------------------------------------------------
ALPHA = string.ascii_uppercase
LETTER_SPACE = set(ALPHA + " ")
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

def sense_ratio(text: str, thr: float=3.5) -> float:
    words = re.findall(r"[A-Z]{1,}", text)
    if not words: return 0.0
    return sum(zipf_frequency(w.lower(), "en")>=thr for w in words)/len(words)

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

def crack(cipher:str,restarts:int,iters:int,lam:float,use_clean:bool,parallel:bool)->Tuple[str,str,float]:
    # First try Caesar
    caesar_plain,caesar_key,ratio=caesar_try(cipher,use_clean)
    if caesar_plain:
        return caesar_key,caesar_plain,ratio

    key, raw, score = crack_once(cipher, restarts, iters, lam,
                                 use_clean, parallel)
    # Escalate if sense ratio poor
    ratio=sense_ratio(clean(raw) if use_clean else raw.upper())
    while ratio < 0.90:
        print(f"[!] Sense {ratio:.0%} – escalating search…")
        restarts *= 3
        iters    *= 3
        lam     *= 1.1           # gently favour real words
        key, raw, score = crack_once(cipher, restarts, iters, lam,
                                    use_clean, parallel)
        plaintext = raw
        ratio = sense_ratio(clean(plaintext) if use_clean else plaintext.upper())
    return key,raw,score

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
    args=ap.parse_args()

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

    key,plain,score=crack(cipher_raw,r,i,args.lam,args.clean,not args.no_parallel)
    print(f"\n[+] Best key  : {key}")
    sr=sense_ratio(clean(plain) if args.clean else plain.upper())
    print(f"[+] Sense‑ratio: {sr:.2%}\n\n===== Decryption =====\n")
    print(plain)

if __name__=='__main__':
    main()