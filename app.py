from flask import Flask, render_template, request, jsonify
import pandas as pd
import os
from openai import OpenAI
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()

app = Flask(__name__)

# グローバル変数
df = None
client = None

# 初期化関数
def initialize():
    global df, client
    if df is None:
        excel_path = os.path.join(os.path.dirname(__file__), '米国での業務内容.xlsx')
        df = pd.read_excel(excel_path, sheet_name='米国での業務内容')
    if client is None:
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            print(f"ERROR: OPENAI_API_KEY not found. Environment variables: {list(os.environ.keys())}")
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        print(f"INFO: OPENAI_API_KEY found (length: {len(api_key)})")
        client = OpenAI(api_key=api_key)

# 管理職とスタッフの判定辞書
management_positions = [
    "部長", "マネージャー", "CFO", "社長", "取締役", "役員", "統括",
    "部門長", "課長", "GM", "ゼネラルマネージャー", "ディレクター",
    "VP", "本部長", "事業部長", "支店長", "所長", "manager", "director",
    "chief", "head", "president", "vice president", "executive"
]

staff_positions = [
    "スタッフ", "社員", "担当", "メンバー", "アシスタント", "アソシエイト",
    "スペシャリスト", "コーディネーター", "staff", "associate", "specialist",
    "coordinator", "assistant", "member", "employee"
]

# 業界・部門の同義語辞書
industry_synonyms = {
    # 業界 - データベースにある値をそのまま使う
    "製薬": "医薬品",
    "薬": "医薬品",
    "医療": "医薬品",
    "ファーマ": "医薬品",
    "おもちゃ": "玩具",
    # IT、自動車などはそのまま
}

department_synonyms = {
    # 部門 - データベースにある値をそのまま使うか、よく使われる別名のみ
    "戦略": "経営企画",
    "企画": "経営企画",
    "経営管理": "経営企画",
    "経営": "経営企画",
    "販売": "営業",
    "セールス": "営業",
    "マーケ": "マーケティング",
    "人材": "人事",
    "HR": "人事",
    "経理": "財務",
    "会計": "財務",
    "開発": "製品開発(R&D)",
    "研究": "製品開発(R&D)",
    "R&D": "製品開発(R&D)",
    "研究開発": "製品開発(R&D)",
    "IT": "システム",
    "情報システム": "システム",
    "法務": "法務・知財",
    "知財": "法務・知財",
    "品質": "品質管理",
    "QA": "品質管理",
    "購買": "調達",
    "資材": "調達",
    "生産": "製造",
    "工場": "製造",
}

def infer_position_category(position):
    """ポジションから管理職かスタッフかを推測（意味ベース）"""
    if not position:
        return ""

    # まずキーワードを抽出（「営業部長」→「営業部長」、「マネージャー職」→「マネージャー」など）
    extracted = extract_keywords(position)
    position_lower = extracted.lower() if extracted else position.lower()

    # 管理職の判定（キーワードが管理職リストに含まれているか、または部分一致）
    for keyword in management_positions:
        keyword_lower = keyword.lower()
        # 双方向チェック: キーワードが入力に含まれる、または入力がキーワードに含まれる
        if keyword_lower in position_lower or position_lower in keyword_lower:
            return "管理職"

    # スタッフの判定
    for keyword in staff_positions:
        keyword_lower = keyword.lower()
        if keyword_lower in position_lower or position_lower in keyword_lower:
            return "スタッフ"

    # 管理職でもスタッフでもない場合はスタッフとして扱う
    return "スタッフ"

def extract_keywords(text):
    """テキストから重要なキーワードを抽出"""
    if not text:
        return ""

    # 不要な単語を除去
    stopwords = ['業界', '部門', '担当', '関連', '系', '分野', 'の', 'する', 'を', 'に', 'で', 'は']

    # キーワード抽出
    keywords = text.strip()
    for word in stopwords:
        keywords = keywords.replace(word, '')

    return keywords.strip()

def normalize_industry(value):
    """業界の類義語を正規化＋キーワード抽出"""
    if not value:
        return ""

    # まず同義語辞書をチェック
    normalized = industry_synonyms.get(value.strip(), None)
    if normalized:
        return normalized

    # 同義語になければキーワード抽出
    return extract_keywords(value)

def normalize_department(value):
    """部門の類義語を正規化＋キーワード抽出"""
    if not value:
        return ""

    # まず同義語辞書をチェック
    normalized = department_synonyms.get(value.strip(), None)
    if normalized:
        return normalized

    # 同義語になければキーワード抽出
    return extract_keywords(value)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/search', methods=['POST'])
def search():
    """直接AI生成を実行（教師信号としてサンプルを参照）"""
    initialize()  # 初回リクエスト時に初期化

    data = request.json
    position = data.get('position', '')
    industry = data.get('industry', '')
    department = data.get('department', '')

    try:
        # 参考サンプルを取得（教師信号として使用）
        reference_samples = get_reference_samples(industry, department)
        # AI生成を実行
        generated_results = generate_job_descriptions(position, industry, department, reference_samples)
        return jsonify({
            'success': True,
            'source': 'ai',
            'results': generated_results
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/generate', methods=['POST'])
def generate():
    """AI生成専用エンドポイント"""
    initialize()

    data = request.json
    position = data.get('position', '')
    industry = data.get('industry', '')
    department = data.get('department', '')

    try:
        # 参考サンプルを取得（業界または部門のいずれかでマッチ）
        reference_samples = get_reference_samples(industry, department)
        generated_results = generate_job_descriptions(position, industry, department, reference_samples)
        return jsonify({
            'success': True,
            'source': 'ai',
            'results': generated_results
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def get_reference_samples(industry, department):
    """参考サンプルを取得（従来の関数、互換性のため残す）"""
    return get_similar_samples(industry, department, 5)

def get_similar_samples(industry, department, count=5):
    """似た業界・部門からサンプルを取得"""
    global df

    # 業界または部門で部分一致検索
    norm_ind = normalize_industry(industry) if industry else ""
    norm_dep = normalize_department(department) if department else ""

    if norm_ind and norm_dep:
        # 両方ある場合はOR検索
        results = df[
            (df["業界"].str.contains(norm_ind, na=False, case=False)) |
            (df["部門"].str.contains(norm_dep, na=False, case=False))
        ]
    elif norm_ind:
        results = df[df["業界"].str.contains(norm_ind, na=False, case=False)]
    elif norm_dep:
        results = df[df["部門"].str.contains(norm_dep, na=False, case=False)]
    else:
        # どちらもなければランダムサンプル
        results = df.sample(min(count, len(df)))

    if len(results) < count:
        return results["職務内容"].tolist()
    return results["職務内容"].sample(count).tolist()

def get_random_samples(count=5):
    """業界・部門に関係なくランダムにサンプルを取得"""
    global df
    return df["職務内容"].sample(min(count, len(df))).tolist()

def search_database(position, industry, department):
    """データベースから似た業界・部門・ポジションで検索してそのまま出力"""
    global df

    # ポジションの推測
    inferred_category = infer_position_category(position)
    search_position = inferred_category if inferred_category else position

    # 正規化
    norm_ind = normalize_industry(industry)
    norm_dep = normalize_department(department)

    # 検索（AND検索）
    results = df[
        (df["ポジション"].str.contains(search_position, na=False, case=False)) &
        (df["業界"].str.contains(norm_ind, na=False, case=False)) &
        (df["部門"].str.contains(norm_dep, na=False, case=False))
    ]

    if not results.empty:
        return results["職務内容"].head(10).tolist()
    else:
        return []

def generate_job_descriptions(position, industry, department, area, reference_samples=None, sample_count=5):
    """ChatGPTで職務内容を生成（文字数チェック付き）"""

    MIN_CHARS = 50  # 最低文字数
    TARGET_COUNT = 10  # 目標件数
    MAX_RETRIES = 5  # 最大リトライ回数（増加）

    all_results = []
    all_generated = []  # フィルタ前の全結果（フォールバック用）
    retry_count = 0

    while len(all_results) < TARGET_COUNT and retry_count < MAX_RETRIES:
        needed = TARGET_COUNT - len(all_results)
        generated = _generate_job_descriptions_raw(position, industry, department, area, reference_samples, sample_count, needed)

        print(f"[DEBUG] リトライ{retry_count+1}: 生成{len(generated)}件", flush=True)
        # 文字数チェック：50文字以上のもののみ採用
        for item in generated:
            char_count = len(item)
            all_generated.append((char_count, item))  # フォールバック用に保存
            if char_count >= MIN_CHARS:
                all_results.append(item)
                print(f"[DEBUG] 採用: {char_count}文字", flush=True)
            else:
                print(f"[DEBUG] 除外: {char_count}文字 - {item[:30]}...", flush=True)
            if len(all_results) >= TARGET_COUNT:
                break

        retry_count += 1

    # 50文字以上が不足している場合、長い順にフォールバック
    if len(all_results) < TARGET_COUNT:
        all_generated.sort(key=lambda x: x[0], reverse=True)  # 長い順
        for char_count, item in all_generated:
            if item not in all_results:
                all_results.append(item)
                print(f"[DEBUG] フォールバック採用: {char_count}文字", flush=True)
                if len(all_results) >= TARGET_COUNT:
                    break

    print(f"[DEBUG] 最終結果: {len(all_results)}件", flush=True)
    return all_results[:TARGET_COUNT]

def _generate_job_descriptions_raw(position, industry, department, area, reference_samples=None, sample_count=5, count=10):
    """ChatGPTで職務内容を生成（内部関数）"""

    # 参考サンプルをプロンプトに含める
    reference_text = ""
    if reference_samples and len(reference_samples) > 0:
        reference_text = "\n\n【フォーマット参考サンプル】以下は文体・長さ・具体性のレベルの参考例です:\n"
        for i, sample in enumerate(reference_samples[:sample_count], 1):
            reference_text += f"{i}. {sample}\n"

    # 担当領域の条件文を作成
    area_condition = f"- 担当領域:{area}" if area else ""
    area_analysis = f'- 「{area}」という担当領域で特に重要な業務は何か' if area else ""

    prompt = f"""以下の条件で、米国ビザ申請書に記載する職務内容を{count}件生成してください。

【条件】
- ポジション:{position}
- 業界:{industry}
- 部門:{department}
{area_condition}
- 勤務地:アメリカ

【ステップ1: 特徴の分析】
まず、以下の点を考えてください（出力不要）：
- 「{industry}」業界の特徴は何か（市場環境、規制、競争要因など）
- 「{department}」部門で重要な業務領域は何か
- 「{position}」として期待される役割・責任は何か
{area_analysis}
- アメリカで行う業務として適切な内容は何か

【ステップ2: 職務内容の生成】
上記の分析を踏まえて、この組み合わせに特有の職務内容を10件生成してください。
{reference_text}
【重要な制約】
- これはアメリカで行う業務内容です。
- 参考サンプルの「内容」は完全に無視してください。参考サンプルは異なる業界・部門のものが含まれています。
- 参考サンプルから学ぶべきは「文体」「1文あたりの長さ」「具体性のレベル」「表現パターン」のみです。
- 生成する内容は、必ず指定された「{industry}」業界の「{department}」部門の業務に限定してください。
- 業界・部門・ポジションの特徴を反映した具体的な内容にしてください。

【文字数の厳守（最重要）】
- 各項目は「最低50文字以上」で記述すること。50文字未満の出力は絶対に不可。
- 目標は60〜80文字。短い文は具体的な情報を追加して必ず50文字以上にすること。
- 例：「営業戦略を立案」(8文字)→NG、「北米市場における新規顧客開拓に向けた営業戦略の立案と、四半期ごとの売上目標達成に向けたアクションプランの策定」(65文字)→OK

【具体性の確保】
- 必ず含めるべき要素：対象（製品/市場/顧客層）、手法・プロセス、目的・成果
- 業界特有の専門用語、規制名、システム名などを積極的に使用すること

【文体の制約】
- 必ず日本語で出力すること（英語や中国語など他の言語は使用しないこと）
- 文体は「です・ます調」ではなく、体言止めや「~する」などの常体で統一すること
- 文末表現は「~を行う」「~に関与」「~を担当」「~の実施」「~を図る」「~を推進」などを使用すること
- 箇条書きで{count}件を番号付きリストで出力すること（分析結果は出力せず、職務内容のみ出力）
"""

    response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": "あなたは米国ビザ申請書に適した職務内容を日本語で生成するアシスタントです。"},
            {"role": "user", "content": prompt}
        ]
    )

    # 生成結果をリストに変換
    content = response.choices[0].message.content
    lines = [line.strip() for line in content.split('\n') if line.strip() and not line.strip().startswith('#')]

    # 番号を除去してリスト化
    job_list = []
    for line in lines:
        # "1. " や "1) " などの番号を除去
        import re
        cleaned = re.sub(r'^\d+[.):]\s*', '', line)
        if cleaned:
            job_list.append(cleaned)

    return job_list

def filter_by_length(items, min_chars=50):
    """50文字以上のものだけを返す"""
    return [item for item in items if len(item) >= min_chars]

def evaluate_patterns(position, industry, department, area, similar_results, random_results):
    """2つのパターンをAIで評価"""

    area_text = f"、担当領域「{area}」" if area else ""

    prompt = f"""以下の2つのパターンで生成された職務内容を評価してください。

【入力条件】
- ポジション: {position}
- 業界: {industry}
- 部門: {department}
{f'- 担当領域: {area}' if area else ''}

【パターンA: 似た業界・部門を参照】
{chr(10).join([f'{i+1}. {item}' for i, item in enumerate(similar_results)])}

【パターンB: ランダムサンプルを参照】
{chr(10).join([f'{i+1}. {item}' for i, item in enumerate(random_results)])}

【評価基準】
1. 業界特性の反映: {industry}業界特有の業務内容が含まれているか
2. 部門特性の反映: {department}部門の典型的な業務が含まれているか
3. ポジション特性の反映: {position}としての役割・責任が適切か
{f'4. 担当領域の反映: {area}に関連する業務が含まれているか' if area else ''}
5. 具体性: 抽象的でなく、具体的な業務内容になっているか
6. 多様性: 似たような内容の繰り返しがなく、多様な業務が含まれているか

【出力形式】
以下のJSON形式で出力してください（他の文章は不要）:
{{
  "winner": "A" または "B" または "同等",
  "score_a": 1-10の整数,
  "score_b": 1-10の整数,
  "reason": "選んだ理由を1-2文で簡潔に"
}}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "あなたは職務内容の品質を評価する専門家です。JSON形式で回答してください。"},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )

        import json
        result = json.loads(response.choices[0].message.content)
        print(f"[EVAL] winner={result.get('winner')}, A={result.get('score_a')}, B={result.get('score_b')}", flush=True)
        return result
    except Exception as e:
        print(f"[EVAL] エラー: {e}", flush=True)
        return {
            "winner": "評価エラー",
            "score_a": 0,
            "score_b": 0,
            "reason": str(e)
        }

@app.route('/api/compare', methods=['POST'])
def compare():
    """3パターン比較用エンドポイント（並列処理版）"""
    initialize()
    print("[COMPARE] v3 - 並列処理 + GPT-4-turbo", flush=True)

    data = request.json
    position = data.get('position', '')
    industry = data.get('industry', '')
    department = data.get('department', '')
    area = data.get('area', '')

    results = {}
    MIN_CHARS = 50

    def generate_similar():
        samples = get_similar_samples(industry, department, 10)
        # generate_job_descriptions内でフィルタ+フォールバック済み
        results = generate_job_descriptions(position, industry, department, area, samples, 10)
        print(f"[COMPARE] similar: {len(results)}件", flush=True)
        return {
            'label': '似た業界・部門 × 10件',
            'samples_used': samples,
            'generated': results
        }

    def generate_random():
        samples = get_random_samples(10)
        # generate_job_descriptions内でフィルタ+フォールバック済み
        results = generate_job_descriptions(position, industry, department, area, samples, 10)
        print(f"[COMPARE] random: {len(results)}件", flush=True)
        return {
            'label': 'ランダム × 10件',
            'samples_used': samples,
            'generated': results
        }

    try:
        # 並列処理でsimilarとrandomを同時生成
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_similar = executor.submit(generate_similar)
            future_random = executor.submit(generate_random)

            results['similar'] = future_similar.result()
            results['random'] = future_random.result()

        # パターン3: データベースから直接出力（AI生成なし）
        db_results = search_database(position, industry, department)
        results['database'] = {
            'label': 'データベース直接',
            'samples_used': [],
            'generated': db_results
        }

        # AI評価を実行
        evaluation = evaluate_patterns(
            position, industry, department, area,
            results['similar']['generated'],
            results['random']['generated']
        )
        results['evaluation'] = evaluation

        return jsonify({
            'success': True,
            'results': results
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
