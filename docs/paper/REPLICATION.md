# Independent replication

*For someone checking this work who did not write it.*

Thank you for doing this. The point is not to confirm the numbers are nice — it
is to find out whether they are **reproducible on a machine that is not the
author's**. A disagreement is a useful result and we want to hear it.

Expect about fifteen minutes, most of it waiting on installs.

---

## What you need

- Linux, or macOS, or Windows with WSL2
- Python 3.10+
- git

**No API keys. No agent runs. No credentials. No cost.** The corpus of recorded
agent traces is committed to the repository; nothing here calls a model.

---

## Run it

```bash
git clone https://github.com/shramanpadhalni-web/quench.git
cd quench
./scripts/setup.sh
./scripts/reproduce.sh
```

---

## What you should see

The script prints five sections. These are the numbers that appear in the paper:

```
events     1398
sessions   147

H1  impure / observable   1 / 16
    rate              6.2%   95% CI [1.1%, 28.3%]
    predicted        20.0%   interval 8-40%
    VERDICT           outside the registered interval

H2  TP 1  FP 1  TN 14  FN 0
    precision         0.50   (target >= 0.80)
    recall            1.00   (target >= 0.70)

H3  1 step promoted by the control-flow-only criterion
    that the oracle classifies as impure
    VERDICT           H3 CONFIRMED
```

Then three workflows seal, one is refused, a six-step workflow executes with
zero model calls, and three refusal paths (tampered signature, drifted input,
revoked artifact) each decline.

**The script exits 0 on success.** If it exits non-zero, that is the finding —
please send the output.

---

## What we are asking you to check

1. **Does it run at all** on your machine, from a clean clone?
2. **Do the numbers match** the block above, exactly?
3. **Does `./docs/paper/build.sh` produce an 8-page PDF?** (needs
   `texlive-latex-base texlive-latex-recommended texlive-fonts-recommended
   texlive-pictures` — the last one is easy to miss; TikZ is not in
   `latex-recommended` despite the name)

---

## Things worth being sceptical about

Please do push on these. They are the parts we are least sure of.

**The baseline is our reimplementation.** `assay/src/assay/strategies/baseline_controlflow_strategy.py`
implements a criterion published by someone else, from its description. The
module docstring records two ambiguities and the reading we chose. If you think
we read it uncharitably, that materially affects H3 and we want to know.

**The oracle definition changed once.** `docs/paper/DEVIATIONS.md` records why,
including the flawed figure it produced. The correction was committed before the
corrected analysis ran — you can check that ordering in the git log.

**The sample is small.** One impure step, sixteen observable. We say so in the
paper. If the confidence interval looks overstated to you, say so.

**The prediction was wrong.** We registered 20% and measured 6.2%. That is
reported as registered rather than adjusted; `docs/paper/PREREGISTRATION.md` was
committed before any data was collected, and the commit date is checkable.

---

## Reporting back

Whatever you find:

- the last ~20 lines of `./scripts/reproduce.sh`
- your OS and Python version
- whether the numbers matched
- anything that struck you as unsound

A short note is plenty. If the numbers do match, we would like to say
"independently reproduced on N machines" in the paper — please tell us whether
you are happy to be named or would prefer to be counted anonymously.
