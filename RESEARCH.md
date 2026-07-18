# Training-Data Research — verified findings (2026-07-17)

Deep-research run: 23 sources fetched, 115 claims extracted, top 25 adversarially verified (3-vote), 24 confirmed / 1 refuted. Everything below survived verification unless marked otherwise.

## Headline: DTW template matching wins for the wand gesture recognizer

- **One training sample per gesture is enough.** uWave (Liu et al., PerCom 2009) hits **93.5% user-dependent accuracy with a single template** per gesture (8-gesture vocab, 3-axis accel), **98.6% with simple template adaptation**, and its 98.4% same-day figure matches HMMs trained on 12 samples each. Crucially, uWave's gestures were segmented by a **Wii-remote button hold — directly analogous to our MPR121 grab**. [paper](https://www.yecl.org/publications/liu09percom.pdf)
- **Jackknife is the best-fit off-the-shelf recognizer** (UCF ISUE lab, CHI 2017): DTW template matcher built for 1–2 examples per gesture, evaluated on handheld Wii-remote accelerometer data (93% @ 1 template, 96% @ 2, on a 25-class set — matching domain-tuned quantized DTW, crushing $3 and Protractor 3D). Has **C++, C#, and dependency-free JavaScript implementations**. Verified preprocessing recipe: **integrate acceleration into 3D position trajectories, then use inner-product local cost on normalized gesture-path direction vectors** (0.93 vs 0.79 accuracy vs squared-Euclidean at 1 template). [github.com/ISUE/Jackknife](https://github.com/ISUE/Jackknife) · [paper](https://cs.ucf.edu/icerc/isuelab/publications/pubs/pn4460-tarnataA.pdf)

## Public datasets: benchmarks, not training sources

Accuracy collapses cross-user on the same data: uWave 98.4% user-dependent → **75.4% user-independent**. So do NOT train on public data — **each person records their own 1–2 templates, ideally same-day** (demo morning!). Datasets worth knowing as benchmarks: uWave (4,480 gestures, accel-only), 6DMG (full 6D incl. gyro), OpenWatch (50 users, 6-axis wrist IMU, gated HF download). Cross-*sensor* transfer magnitude is unquantified (the one claim quantifying it was refuted 1-2).

## If we need the neural-net fallback

- **stefan-spiss/MagicWand-TFLite-ESP32-MPU6050** — complete working pipeline on our *exact* hardware (serial-logger capture sketch, Colab CNN training notebook, TFLM inference; wing/ring/slope + negative class). Caveats: accel-only (gyro unused), single-person example data. [repo](https://github.com/stefan-spiss/MagicWand-TFLite-ESP32-MPU6050)
- **Edge Impulse budget: ~3 minutes of data per class** (Spectral Analysis + small Keras net, optional K-means anomaly rejection) — vendor guidance for *continuous* windows, transfers only approximately to segmented gestures.
- **Skip Google's Magic Wand codelab**: wrong hardware (Nano 33 BLE / LSM9DS1), no training tooling, stale links (TFLM example removed from master; successor petewarden/magic_wand).

## Part (b) — gesture→music ranking: NO verified findings

Zero claims about conducting-gesture-to-music mapping, Wekinator-style interactive ML, or ranker bootstrap strategies survived verification (they were surfaced but fell below the verify budget). Our heuristic-first + thumbs-feedback plan stands on engineering judgment, not cited evidence. **Unverified leads** from the search phase if we want to dig later: CONDUCT dataset (LREC 2018, mocap conducting gestures for sound control), MusicRL (DeepMind, preference-aligned music gen), Fiebrink's Wekinator (NIME 2009).

## Impact on our plan

1. **Classifier**: keep DTW, adopt the Jackknife recipe (accel→position integration, inner-product local cost on direction vectors) inside `server/gestures/classify.py`; dtaidistance remains fine as the DTW engine, or port Jackknife's JS/C++ directly.
2. **Data burden drops**: 1–2 templates per gesture per user replaces the planned 30–50 samples/class. Still record ~10–20 extra reps per gesture for eval + rejection-threshold tuning.
3. **Operational rule**: whoever demos records their own templates that morning (cross-user = ~75%, cross-day = 93.5%; same-day same-user = ~98%).
4. **Open question to test ourselves**: how much the gyro adds over accel-only (none of the verified evidence uses it), and how well DTW rejects out-of-vocabulary grabbed motions (threshold tuning matters).
