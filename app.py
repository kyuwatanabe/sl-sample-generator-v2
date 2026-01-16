from flask import Flask, render_template, request, jsonify
import pandas as pd
import os
from openai import OpenAI
from dotenv import load_dotenv

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

def generate_job_descriptions(position, industry, department, reference_samples=None, sample_count=5):
    """ChatGPTで職務内容を生成"""

    # 参考サンプルをプロンプトに含める
    reference_text = ""
    if reference_samples and len(reference_samples) > 0:
        reference_text = "\n\n【フォーマット参考サンプル】以下は文体・長さ・具体性のレベルの参考例です:\n"
        for i, sample in enumerate(reference_samples[:sample_count], 1):
            reference_text += f"{i}. {sample}\n"

    prompt = f"""以下の条件で、米国ビザ申請書に記載する職務内容を生成してください。

【条件】
- ポジション:{position}
- 業界:{industry}
- 部門:{department}
- 勤務地:アメリカ

【ステップ1: 特徴の分析】
まず、以下の点を考えてください（出力不要）：
- 「{industry}」業界の特徴は何か（市場環境、規制、競争要因など）
- 「{department}」部門で重要な業務領域は何か
- 「{position}」として期待される役割・責任は何か
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

【文体の制約】
- 必ず日本語で出力すること（英語や中国語など他の言語は使用しないこと）
- 各文は1~2文以内で簡潔に、業務内容を具体的に記述すること
- 文体は「です・ます調」ではなく、体言止めや「~する」などの常体で統一すること
- 文末表現は「~を行う」「~に関与」「~を担当」「~の実施」「~を図る」「~を推進」などを使用すること
- 箇条書きで10件を番号付きリストで出力すること（分析結果は出力せず、職務内容のみ出力）
"""

    response = client.chat.completions.create(
        model="gpt-4",
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

    return job_list[:10]

@app.route('/api/compare', methods=['POST'])
def compare():
    """3パターン比較用エンドポイント"""
    initialize()

    data = request.json
    position = data.get('position', '')
    industry = data.get('industry', '')
    department = data.get('department', '')

    results = {}

    try:
        # パターン1: 似た業界・部門 × 10件
        samples_similar = get_similar_samples(industry, department, 10)
        results['similar'] = {
            'label': '似た業界・部門 × 10件',
            'samples_used': samples_similar,
            'generated': generate_job_descriptions(position, industry, department, samples_similar, 10)
        }

        # パターン2: ランダム × 10件
        samples_random = get_random_samples(10)
        results['random'] = {
            'label': 'ランダム × 10件',
            'samples_used': samples_random,
            'generated': generate_job_descriptions(position, industry, department, samples_random, 10)
        }

        # パターン3: データベースから直接出力（AI生成なし）
        db_results = search_database(position, industry, department)
        results['database'] = {
            'label': 'データベース直接',
            'samples_used': [],
            'generated': db_results
        }

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
