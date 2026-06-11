# -*- coding: utf-8 -*-
"""
付録B 実験ハーネス（E1–E4） — multilayer_sim_v2.py（コアモデル＝B.9掲載分）を用いて
付録Bの各実験を再現する。

使い方:
    python3 reproduce_appendix_B.py [e1|e2|e3|e41|e42|e43|e44|all]
      e1 = 基準条件の固定化(B.3)      e2 = 16構成の必要条件構造(B.4)
      e3 = 介入タイミングと遅延費用(B.5)
      e41= 判断余力の臨界性(B.6.1)    e42= 一次元感度(B.6.2)
      e43= 大域感度LHS(B.6.3)        e44= 選択規則の頑健性ロジット(B.6.4)

Python3・標準ライブラリのみ。乱数シードは試行番号で管理し、結果は再現可能。
"""
import sys, random
from multilayer_sim_v2 import P, Levers, run, experiment


# ============================================================================
# 付録B 実験ハーネス（E1–E4）
#   本セクションは上記コアモデル（step/run/experiment）を用いて、付録Bの各実験を
#   再現する。コマンド: python3 <file>.py [e1|e3|e41|e42|e43|e44|all]
#   いずれも Python3・標準ライブラリのみ。乱数シードは試行番号で管理し再現可能。
# ============================================================================

# 感度分析の対象とする主要14パラメータ（いずれも step() 内で動的に参照され、
# State の初期値には焼き付かないため、P の上書きがそのまま挙動に反映される）
PARAMS14 = ['harm', 'I_consult', 'F_consult_pi', 'cost_T', 'load_T', 'esc_pen',
            'info_pen', 'I_org', 'F_org', 'I_formal', 'F_formal',
            'p_res_org', 'p_res_solo', 'formal_pi_damage']

def experiment_ov(lv, overrides=None, n=1000, turns=100):
    """P を一時的に上書きして experiment() を実行し、確実に元へ戻す。"""
    if overrides:
        saved = {k: P[k] for k in overrides}
        P.update(overrides)
        try:
            return experiment(lv, n=n, turns=turns)
        finally:
            P.update(saved)
    return experiment(lv, n=n, turns=turns)

# ---------------- E1：基準条件（B.3） ----------------
def run_E1(n=1000):
    print(f"E1: 基準条件における固定化の創発（B.3, n={n}）")
    r = experiment(Levers(), n=n)
    print(f"  固定化率        = {r['lock']:.1%}")
    print(f"  二重ロックイン  = {r['dbl']:.1%}")
    print(f"  形式的対応 平均 = {r['formal']:.2f} 回")
    print(f"  曝露総量        = {r['expo']:.1f}")
    print(f"  解決率          = {r['res_rate']:.1%}")


# ---------------- E2：介入レバーの必要条件構造（B.4） ----------------
def run_E2(n=1000):
    from itertools import product
    print(f"E2: 介入レバーの必要条件構造（16構成 x 早期/事後, n={n}）")
    print(f"{'構成':>12} {'早期(t=0)':>12} {'事後(t=50)':>12}")
    for combo in product((0, 1), repeat=4):
        nm = ''.join(d for d, b in zip('1234', combo) if b)
        name = ('L' + nm) if nm else 'なし'
        early = experiment(Levers(*map(bool, combo), start=0), n=n)['lock']
        late  = experiment(Levers(*map(bool, combo), start=50), n=n)['lock']
        print(f"{name:>12} {early:12.1%} {late:12.1%}")

# ---------------- E3：介入タイミングと遅延の費用（B.5） ----------------
def run_E3(starts=(0, 10, 20, 30, 40, 50, 60, 70, 80), n=1000):
    """四レバー同時供給。観察期間を「介入開始から60ターン」に固定（B.2）。
    解決ターンは介入開始 t0 を基準とする相対値（=介入開始から解決までの所要）。"""
    print(f"E3: 介入タイミングと遅延の費用（四レバー, 観察=開始から60ターン, n={n}）")
    print(f"{'開始t':>6} {'固定化':>8} {'解決率':>8} {'解決ターン(開始基準)':>20} {'曝露総量':>10}")
    rows = []
    for t0 in starts:
        lv = Levers(True, True, True, True, start=t0)
        turns = t0 + 60
        locks = 0; expo = 0.0; rel = []
        for k in range(n):
            st = run(lv, turns, seed=k)
            fix = (st.tail_attack >= 5)
            locks += fix
            expo += st.exposure
            # 介入開始以降に解決し、固定化していない試行のみを母数とする
            if (not st.attack_on) and (not fix) and st.res_turn >= t0:
                rel.append(st.res_turn - t0)
        mrt = sum(rel) / len(rel) if rel else float('nan')
        rows.append((t0, locks / n, len(rel) / n, mrt, expo / n))
        print(f"{t0:6d} {locks/n:8.1%} {len(rel)/n:8.1%} {mrt:20.1f} {expo/n:10.1f}")
    return rows

# ---------------- E4.1：判断余力供給の臨界性（B.6.1） ----------------
def run_E4_critical(scales=None, n=600):
    """L2レバーの供給強度を基準値の0〜2倍に掃引（早期, L2単独）。"""
    if scales is None:
        scales = [round(0.1 * i, 1) for i in range(0, 21)]
    base = {k: P[k] for k in ('L2_Sstar', 'L2_S_T', 'L2_S_B', 'L2_I_B')}
    print(f"E4.1: L2供給強度の臨界性（早期, L2単独, n={n}）")
    print(f"{'L2強度':>7} {'固定化':>8}")
    for s in scales:
        ov = {k: base[k] * s for k in base}
        r = experiment_ov(Levers(L2=True), ov, n=n)
        print(f"{s:7.1f} {r['lock']:8.1%}")

# ---------------- 主要な質的主張の判定（E4.2/E4.3共通） ----------------
# OATで「全主張成立」を判定する中核5主張
OAT_KEYS = ['無介入で固定化支配的', '早期四レバー有効', '事後解除にL3必須',
            'L3L4単独は無効', 'ヒステリシス']
# LHS（図B-4）で成立率を報告する5主張
LHS_KEYS = ['無介入で固定化支配的', '事後解除にL3必須', 'L3L4単独は無効',
            'ヒステリシス', '事後回復可能(四レバー)']

def _check_claims(n=300):
    base    = experiment(Levers(), n=n)['lock']
    fe0     = experiment(Levers(True, True, True, True, start=0), n=n)['lock']
    fe50    = experiment(Levers(True, True, True, True, start=50), n=n)['lock']
    l1l2_0  = experiment(Levers(L1=True, L2=True, start=0), n=n)['lock']
    l1l2_50 = experiment(Levers(L1=True, L2=True, start=50), n=n)['lock']
    l3      = experiment(Levers(L3=True), n=n)['lock']
    l4      = experiment(Levers(L4=True), n=n)['lock']
    return {
        '無介入で固定化支配的':   base > 0.5,
        '早期四レバー有効':       fe0 < 0.10,
        '事後解除にL3必須':       l1l2_50 > 0.5,            # L3を欠くL1L2は事後無効
        'L3L4単独は無効':         (l3 > 0.5) and (l4 > 0.5),
        'ヒステリシス':           (l1l2_0 < 0.10) and (l1l2_50 > 0.5),
        '事後回復可能(四レバー)': fe50 < 0.10,              # 参考: 条件依存（≈49%）
    }

# ---------------- E4.2：一次元±50%感度（B.6.2） ----------------
def run_E4_oat(n=300):
    print(f"E4.2: 一次元±50%感度（主要14パラメータ, n={n}）")
    cases = []
    for key in PARAMS14:
        for label, fac in (('+50%', 1.5), ('-50%', 0.5)):
            saved = {key: P[key]}; P.update({key: P[key] * fac})
            try:
                c = _check_claims(n)
            finally:
                P.update(saved)
            allhold = all(c[k] for k in OAT_KEYS)
            cases.append((key, label, allhold))
            ng = [k for k in OAT_KEYS if not c[k]]
            print(f"{key:>16} {label:>5}: {'全主張成立' if allhold else '不成立=' + ','.join(ng)}")
    nhold = sum(1 for _, _, h in cases if h)
    print(f"→ {nhold}/{len(cases)} ケースで主要な質的主張がすべて成立")

# ---------------- E4.3：大域感度（LHS, B.6.3） ----------------
def run_E4_lhs(samples=150, n=300, seed=12345):
    rng = random.Random(seed)
    D = len(PARAMS14)
    strata = []
    for _ in range(D):
        idx = list(range(samples)); rng.shuffle(idx); strata.append(idx)
    base = {k: P[k] for k in PARAMS14}
    counts = {k: 0 for k in LHS_KEYS}
    for s in range(samples):
        ov = {}
        for d, key in enumerate(PARAMS14):
            u = (strata[d][s] + rng.random()) / samples   # 0..1
            ov[key] = base[key] * (0.5 + u)               # 係数 0.5..1.5（±50%）
        saved = {k: P[k] for k in ov}; P.update(ov)
        try:
            c = _check_claims(n)
        finally:
            P.update(saved)
        for k in LHS_KEYS:
            counts[k] += c[k]
    print(f"E4.3: 大域感度（LHS {samples}標本, 各n={n}）")
    for k in LHS_KEYS:
        print(f"  {k:<22}: {counts[k]/samples:.0%}")

# ---------------- E4.4：選択規則の頑健性（ロジット, B.6.4） ----------------
def run_E4_logit(betas=(10, 20, 40), n=500):
    conds = {
        '基準条件':       Levers(),
        '四レバー(t=0)':  Levers(True, True, True, True, start=0),
        'L1L2(t=50)':     Levers(L1=True, L2=True, start=50),
        '四レバー(t=50)': Levers(True, True, True, True, start=50),
    }
    print(f"E4.4: ロジット選択下の固定化率（n={n}）")
    print(f"{'β':>4} " + "".join(f"{name:>16}" for name in conds))
    for b in betas:
        cells = []
        for name, lv in conds.items():
            r = experiment_ov(lv, {'beta': b}, n=n)
            cells.append(f"{r['lock']:16.1%}")
        print(f"{b:4d} " + "".join(cells))

# ---------------- ディスパッチャ ----------------
def _run_all():
    for fn in (run_E1, run_E2, run_E3, run_E4_critical, run_E4_oat, run_E4_lhs, run_E4_logit):
        fn(); print()

_DISPATCH = {'e1': run_E1, 'e2': run_E2, 'e3': run_E3, 'e41': run_E4_critical,
             'e42': run_E4_oat, 'e43': run_E4_lhs, 'e44': run_E4_logit, 'all': _run_all}


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'all'
    fn = _DISPATCH.get(cmd)
    if fn is None:
        print("usage: python3 reproduce_appendix_B.py [e1|e2|e3|e41|e42|e43|e44|all]")
        sys.exit(1)
    fn()
