# -*- coding: utf-8 -*-
"""
多重ゲーム構造の統合シミュレーション v2（本実装）

設計判断（確定）:
  D1 保護者は被害側のみ / D2 全主体同型の評価関数 / D3 δは閾値特性のみ
  K1 付録は二分（A=モデル仕様, B=実験と結果）
  K2 Mの行為集合に「形式的対応」を追加（4.7.3 状況2の明示的実装）
  K3 Bを主体化: {支援, 形式確認}（「形式確認」は2.5.2 制度化のパラドックスの実装）
  K4 選択規則は決定論的最大化。同値時は対応側を優先（旧付録B規則の踏襲）

結合規則（本文アンカー）:
  C1  V沈黙 → T認知低下・情報ペナルティ          … 4.7.2 状況1
  C2  M形式的対応 → 見かけの沈静化・π_V毀損・免罪符 … 4.7.3 状況2
  C3  G外部化 → S_T/S_M急上昇・係争コスト          … 4.7.4 状況3
  C4  T不対応の反復 → π_V漸減                      … 5.3 類型B
  C5  案件抱え込み → S_T累積 → δ_T≈0               … 5.2 類型A
  C6  M組織対応 → Tのコスト分散・負荷軽減          … 9.3.4
  C7  制裁経験 → PのR学習                          … 旧付録A
  C8  組織的応答 → G信頼回復・係争収束             … 9.3.3
  C9  B支援 → M/Tの負荷低減・組織化の後押し        … 9.3.5
  C10 B形式確認 → 文書要求によるS_T/S_M微増        … 2.5.2
"""
import random
from dataclasses import dataclass

# ---------------- パラメータ（感度掃引の対象は P に集約） ----------------
P = dict(
    beta=None,
    delta_low=0.05,
    Sstar_V=1.0, Sstar_T=1.0, Sstar_M=1.0, Sstar_B=1.0,
    # 児童生徒間
    S_V0=0.20, harm=0.13, S_V_decay=0.06, S_V_cap=2.0,
    I_attack=0.40, F_attack_R=-1.4, F_stop=0.15, R0=0.15,
    I_consult=-0.75, F_consult_pi=1.6, I_silent=-0.10, F_silent=-0.35, pi0=0.45,
    # 教員
    S_T0=0.60, load_T=0.12, S_cap=2.2,
    base_detect=0.10, consult_detect=0.85,
    cost_T=0.65, esc_pen=0.40, org_relief=0.30, info_pen=0.25,
    I_wait=-0.05, F_wait=-0.35, eff0=0.35, eff_gain=0.20, eff_decay=0.01,
    # 保護者
    trust0=0.70, trust_drop_wait=0.10, trust_drop_resp=0.05,
    I_esc=-0.30, F_esc=1.1, F_coop=0.7, esc_S_shock=0.45,
    trust_repair=0.15, deesc_trust=0.55, trust_gain_res=0.20,
    # 学校組織 M
    S_M0=0.55, load_M=0.08,
    I_org=-0.60, F_org=1.0, I_formal=-0.10, F_formal=0.5, formal_diminish=0.6,
    I_deleg=0.0, F_deleg=-0.7,
    formal_pi_damage=0.15, formal_R_damage=0.05, formal_trust_gain=0.08,
    formal_S_M_relief=0.10, org_S_T_relief=0.15,
    risk0=0.25, risk_dur=0.02, risk_esc=0.40,
    # 設置者 B
    S_B0=0.50, load_B=0.04, esc_B_shock=0.10, aware_B_dur=15,
    I_support=-0.45, F_support=1.0, I_check=-0.05, F_check=-0.40,
    riskB0=0.20, riskB_dur=0.02, riskB_esc=0.50,
    support_S_M=0.15, support_S_T=0.10, support_org_bonus=0.10,
    check_S_load=0.05,
    # 解決
    p_res_org=0.45, p_res_solo=0.10,
    R_gain_org=0.45, R_gain_solo=0.10,
    pi_gain=0.25, pi_gain_L3=0.40, pi_decay=0.10, pi_decay_L3=0.05,
    # レバー
    L1_T=0.25, L1_M=0.10,
    L2_Sstar=0.30, L2_S_T=0.07, L2_S_B=0.10, L2_I_B=0.20,
    L3_pi_floor=0.10, L3_eff_ceil=0.40, L3_eff_rec=0.03,
    L4_detect=0.35, L4_info_factor=0.4,
)

@dataclass
class Levers:
    L1: bool = False; L2: bool = False; L3: bool = False; L4: bool = False
    start: int = 0

@dataclass
class State:
    attack_on: bool = True
    S_V: float = P['S_V0']
    pi_V: float = P['pi0']
    R_P: float = P['R0']
    aware_T: bool = False
    S_T: float = P['S_T0']
    eff_T: float = P['eff0']
    trust_G: float = P['trust0']
    escalated: bool = False
    aware_M: bool = False
    S_M: float = P['S_M0']
    organized: bool = False
    formal_count: int = 0
    aware_B: bool = False
    S_B: float = P['S_B0']
    b_support: bool = False
    silent: bool = False
    unresolved: int = 0       # 累積。攻撃停止後もリセットしない（履歴依存。C5でS_T累積に作用）
    exposure: float = 0.0     # Σ S_V（被害曝露総量）
    tail_attack: int = 0      # 最終10ターン中の攻撃ターン数
    res_turn: int = -1        # 最終停止ターン（攻撃が最後にFalseになったt）。
                              # 最終状態が非攻撃の試行では解決ターンに一致する。


def pick(rng, options):
    """options: [(key, U), ...] 先頭が「対応側」。決定論時は同値で先頭優先。
    P['beta'] が None 以外のときはロジット選択（E4頑健性確認用）。"""
    beta = P.get('beta')
    if beta is None:
        best = max(u for _, u in options)
        for k, u in options:
            if u == best:
                return k
    import math
    mx = max(u for _, u in options)
    ws = [math.exp(beta * (u - mx)) for _, u in options]
    s = sum(ws); r = rng.random() * s; acc = 0.0
    for (k, _), w in zip(options, ws):
        acc += w
        if r <= acc:
            return k
    return options[-1][0]

def delta(S, Sstar):
    return 1.0 if S < Sstar else P['delta_low']

def step(st: State, lv: Levers, t: int, rng) -> State:
    on = t >= lv.start
    L1, L2, L3, L4 = (lv.L1 and on), (lv.L2 and on), (lv.L3 and on), (lv.L4 and on)
    Sstar_T = P['Sstar_T'] + (P['L2_Sstar'] if L2 else 0.0)
    if L2:
        st.S_T = max(0.0, st.S_T - P['L2_S_T'])          # 基底業務削減（制度設計水準）
        st.S_B = max(0.0, st.S_B - P['L2_S_B'])
    if L3:                                                # 研修・成功事例共有による期待の再形成
        if st.eff_T < P['L3_eff_ceil']:
            st.eff_T = min(P['L3_eff_ceil'], st.eff_T + P['L3_eff_rec'])

    # --- 加害生徒 P（毎ターン判断：停止後の再発も評価構造の帰結として許容） ---
    U_at = P['I_attack'] + P['F_attack_R'] * st.R_P
    U_st = 0.0 + P['F_stop']
    if st.attack_on:
        if pick(rng, [('attack', U_at), ('stop', U_st)]) == 'stop':
            st.attack_on = False
            st.res_turn = t
    else:
        if pick(rng, [('stop', U_st), ('attack', U_at)]) == 'attack':
            st.attack_on = True

    # --- 被害生徒 V ---
    consulted = False
    if st.attack_on:
        st.S_V = min(P['S_V_cap'], st.S_V + P['harm'])
        st.exposure += st.S_V
        d = delta(st.S_V, P['Sstar_V'])
        U_c = P['I_consult'] + d * P['F_consult_pi'] * st.pi_V
        U_s = P['I_silent'] + d * P['F_silent']
        consulted = pick(rng, [('consult', U_c), ('silent', U_s)]) == 'consult'
        st.silent = not consulted
    else:
        st.S_V = max(0.0, st.S_V - P['S_V_decay'])

    # --- 教員 T: 認知 [C1][L4] ---
    if st.attack_on and not st.aware_T:
        p = P['consult_detect'] if consulted else P['base_detect']
        if L4:
            p = min(1.0, p + P['L4_detect'])
        if rng.random() < p:
            st.aware_T = True

    # --- 教員 T: {対応, 様子見} ---
    responded = False
    if st.attack_on and st.aware_T:
        st.unresolved += 1
        st.S_T = min(P['S_cap'], st.S_T + P['load_T'])    # [C5]
        d = delta(st.S_T, Sstar_T)
        cost = P['cost_T']
        if st.escalated: cost += P['esc_pen']             # [C3]
        if st.organized: cost -= P['org_relief']          # [C6]
        if L1: cost -= P['L1_T']
        pen = P['info_pen'] if st.silent else 0.0
        if L4: pen *= P['L4_info_factor']
        U_r = -(cost + pen) + d * st.eff_T
        U_w = P['I_wait'] + d * P['F_wait']
        responded = pick(rng, [('respond', U_r), ('wait', U_w)]) == 'respond'

    # --- 保護者 G: {協働, 外部化} ---
    if st.attack_on and st.S_V > 0.6:
        st.trust_G = max(0.0, st.trust_G - (P['trust_drop_resp'] if responded else P['trust_drop_wait']))
        U_e = P['I_esc'] + P['F_esc'] * (1.0 - st.trust_G)
        U_c2 = 0.0 + P['F_coop'] * st.trust_G
        if (not st.escalated) and pick(rng, [('coop', U_c2), ('esc', U_e)]) == 'esc':
            st.escalated = True                            # [C3]
            st.S_T = min(P['S_cap'], st.S_T + P['esc_S_shock'])
            st.S_M = min(P['S_cap'], st.S_M + P['esc_S_shock'])
            st.S_B = min(P['S_cap'], st.S_B + P['esc_B_shock'])

    # --- 学校組織 M: {組織対応, 形式的対応, 担任任せ} [K2] ---
    if st.attack_on and (responded or st.escalated):
        st.aware_M = True
    if st.attack_on and st.aware_M and not st.organized:
        st.S_M = min(P['S_cap'], st.S_M + P['load_M'])
        d = delta(st.S_M, P['Sstar_M'])
        risk = min(1.0, P['risk0'] + P['risk_dur'] * st.unresolved
                   + (P['risk_esc'] if st.escalated else 0.0))
        I_o = P['I_org'] + (P['L1_M'] if L1 else 0.0) + (P['support_org_bonus'] if st.b_support else 0.0)
        U_o = I_o + d * P['F_org'] * risk
        U_f = P['I_formal'] + d * P['F_formal'] * risk * (P['formal_diminish'] ** st.formal_count)
        U_d = P['I_deleg'] + d * P['F_deleg'] * risk
        choice_M = pick(rng, [('org', U_o), ('formal', U_f), ('deleg', U_d)])
        if choice_M == 'org':                              # 同値時は対応側優先 [K4]
            st.organized = True
            st.S_T = max(0.0, st.S_T - P['org_S_T_relief'])  # [C6]
        elif choice_M == 'formal':                         # [C2] 形式的対応
            st.formal_count += 1
            st.S_M = max(0.0, st.S_M - P['formal_S_M_relief'])
            st.trust_G = min(1.0, st.trust_G + P['formal_trust_gain'])
            st.pi_V = max(0.0, st.pi_V - P['formal_pi_damage'])     # 期待の毀損
            st.R_P = max(0.05, st.R_P - P['formal_R_damage'])       # 免罪符

    # --- 設置者 B: {支援, 形式確認} [K3] ---
    st.b_support = False
    if st.attack_on and (st.escalated or st.unresolved >= P['aware_B_dur']):
        st.aware_B = True
    if st.attack_on and st.aware_B:
        st.S_B = min(P['S_cap'], st.S_B + P['load_B'])
        d = delta(st.S_B, P['Sstar_B'])
        riskB = min(1.0, P['riskB0'] + P['riskB_dur'] * st.unresolved
                    + (P['riskB_esc'] if st.escalated else 0.0))
        I_s = P['I_support'] + (P['L2_I_B'] if L2 else 0.0)
        U_s2 = I_s + d * P['F_support'] * riskB
        U_k = P['I_check'] + d * P['F_check'] * riskB
        if pick(rng, [('support', U_s2), ('check', U_k)]) == 'support':  # [C9]
            st.b_support = True
            st.S_M = max(0.0, st.S_M - P['support_S_M'])
            st.S_T = max(0.0, st.S_T - P['support_S_T'])
        else:                                              # [C10] 制度化のパラドックス
            st.S_T = min(P['S_cap'], st.S_T + P['check_S_load'])
            st.S_M = min(P['S_cap'], st.S_M + P['check_S_load'])

    # --- 係争の収束 [C8] ---
    if st.escalated and st.organized and responded:
        st.trust_G = min(1.0, st.trust_G + P['trust_repair'])
        if st.trust_G > P['deesc_trust']:
            st.escalated = False

    # --- 解決判定と学習 ---
    if st.attack_on and responded:
        p_res = P['p_res_org'] if st.organized else P['p_res_solo']
        if rng.random() < p_res:
            st.attack_on = False
            st.res_turn = t
            st.R_P = min(1.0, st.R_P + (P['R_gain_org'] if st.organized else P['R_gain_solo']))  # [C7]
            st.pi_V = min(1.0, st.pi_V + (P['pi_gain_L3'] if L3 else P['pi_gain']))
            st.eff_T = min(1.0, st.eff_T + P['eff_gain'])
            st.trust_G = min(1.0, st.trust_G + P['trust_gain_res'])
    elif st.attack_on and st.aware_T and not responded:
        st.pi_V = max(0.0, st.pi_V - (P['pi_decay_L3'] if L3 else P['pi_decay']))  # [C4]
        st.eff_T = max(0.0, st.eff_T - P['eff_decay'])
    if L3:
        st.pi_V = max(st.pi_V, P['L3_pi_floor'])           # 即日対応規範による期待の床
    return st


def run(lv: Levers, turns=100, seed=0):
    rng = random.Random(seed)
    st = State()
    for t in range(turns):
        st = step(st, lv, t, rng)
        if t >= turns - 10 and st.attack_on:
            st.tail_attack += 1
    return st

def experiment(lv: Levers, n=1000, turns=100):
    agg = dict(lock=0, typeB=0, typeA=0, dbl=0, esc=0, formal=0.0, expo=0.0)
    res = []  # 解決ターン: 「非攻撃で終了 かつ 非固定化」の試行のみを母数とする
    for k in range(n):
        st = run(lv, turns, seed=k)
        a = st.S_T >= P['Sstar_T']
        b = st.pi_V < 0.10
        fixated = (st.tail_attack >= 5)        # 窓判定：最終10ターンの過半で攻撃継続
        agg['lock'] += fixated
        agg['typeA'] += a
        agg['typeB'] += b
        agg['dbl'] += (a and b)
        agg['esc'] += st.escalated
        agg['formal'] += st.formal_count
        agg['expo'] += st.exposure
        # 解決ターン(=最終停止ターン)は「解決(非攻撃終了)かつ非固定化」に限定して集計する。
        # これにより、固定化フラグが立ったまま最終ターンで停止した試行が解決ターン平均に
        # 混入する可能性を構造的に排除する（母数=解決した試行に限定）。
        if (not st.attack_on) and (not fixated):
            res.append(st.res_turn)
    n = float(n)
    mrt = sum(res) / len(res) if res else float('nan')
    return dict(lock=agg['lock']/n, typeA=agg['typeA']/n, typeB=agg['typeB']/n,
                dbl=agg['dbl']/n, esc=agg['esc']/n, formal=agg['formal']/n,
                expo=agg['expo']/n,
                res_rate=len(res)/n,   # 解決率（解決ターン平均mrtの母数割合）
                mrt=mrt)               # 解決ターン平均。res_rateと併記して用いること（A.9参照）

def report(conds, n=1000):
    # 主指標は固定化率・二重ロックイン・形式的対応回数・曝露総量。
    # 解決ターン平均(mrt)は解決率が高い介入条件でのみ代表性を持つため（A.9）、
    # 本表では解決率のみ示し、mrtはreport_timing()でE3条件について別途報告する。
    print(f"{'条件':<22} 固定化   二重    形式的対応  曝露総量  解決率")
    for name, lv in conds.items():
        r = experiment(lv, n)
        print(f"{name:<22} {r['lock']:6.1%}  {r['dbl']:6.1%}  {r['formal']:7.2f}   {r['expo']:7.1f}  {r['res_rate']:6.1%}")

def report_timing(conds, n=1000):
    # E3用: 解決率がほぼ100%の介入条件について、解決ターン平均(mrt)を解決率と併記する。
    print(f"{'条件':<22} 固定化   解決率   解決ターン平均  曝露総量")
    for name, lv in conds.items():
        r = experiment(lv, n)
        print(f"{name:<22} {r['lock']:6.1%}  {r['res_rate']:6.1%}  {r['mrt']:10.1f}     {r['expo']:7.1f}")

if __name__ == '__main__':
    conds = {
        'ベースライン':        Levers(),
        'L1のみ':              Levers(L1=True),
        'L2のみ':              Levers(L2=True),
        'L3のみ':              Levers(L3=True),
        'L4のみ':              Levers(L4=True),
        '四レバー（t=0）':     Levers(True, True, True, True, start=0),
        'L1+L2（t=0）':        Levers(L1=True, L2=True, start=0),
        'L1+L2（t=50）':       Levers(L1=True, L2=True, start=50),
        '四レバー（t=50）':    Levers(True, True, True, True, start=50),
    }
    report(conds)
    print()
    timing = {
        '四レバー（t=0）':  Levers(True, True, True, True, start=0),
        '四レバー（t=20）': Levers(True, True, True, True, start=20),
        '四レバー（t=50）': Levers(True, True, True, True, start=50),
    }
    report_timing(timing)
