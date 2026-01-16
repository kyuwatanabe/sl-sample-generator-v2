document.addEventListener('DOMContentLoaded', function() {
    const searchForm = document.getElementById('searchForm');
    const loading = document.getElementById('loading');
    const loadingText = document.querySelector('#loading p');
    const compareResults = document.getElementById('compareResults');
    const error = document.getElementById('error');

    searchForm.addEventListener('submit', async function(e) {
        e.preventDefault();

        const position = document.getElementById('position').value;
        const industry = document.getElementById('industry').value;
        const department = document.getElementById('department').value;

        // 入力チェック
        if (!position && !industry && !department) {
            showError('少なくとも1つの項目を入力してください');
            return;
        }

        // UI更新
        loadingText.textContent = '3パターン生成中です。30秒程度かかります...';
        loading.style.display = 'block';
        compareResults.style.display = 'none';
        error.style.display = 'none';

        try {
            const response = await fetch('/api/compare', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    position: position,
                    industry: industry,
                    department: department
                })
            });

            const data = await response.json();

            if (data.success) {
                displayCompareResults(data.results);
            } else {
                showError(data.error || '生成中にエラーが発生しました');
            }
        } catch (err) {
            showError('サーバーとの通信に失敗しました: ' + err.message);
        } finally {
            loading.style.display = 'none';
        }
    });

    function displayCompareResults(results) {
        const patterns = ['similar', 'random'];

        patterns.forEach(pattern => {
            const data = results[pattern];

            // 参照したサンプルを表示
            const samplesEl = document.getElementById('samples_' + pattern);
            samplesEl.innerHTML = '';
            data.samples_used.forEach(sample => {
                const li = document.createElement('li');
                li.textContent = sample.substring(0, 50) + (sample.length > 50 ? '...' : '');
                samplesEl.appendChild(li);
            });

            // 生成結果を表示
            const generatedEl = document.getElementById('generated_' + pattern);
            generatedEl.innerHTML = '';
            data.generated.forEach((item, index) => {
                const div = document.createElement('div');
                div.className = 'mb-2 small';
                div.innerHTML = `<strong>${index + 1}.</strong> ${item}`;
                generatedEl.appendChild(div);
            });
        });

        // データベース直接パターン
        const dbData = results['database'];
        const dbGeneratedEl = document.getElementById('generated_database');
        dbGeneratedEl.innerHTML = '';
        if (dbData.generated.length === 0) {
            dbGeneratedEl.innerHTML = '<p class="text-muted">該当するサンプルがありません</p>';
        } else {
            dbData.generated.forEach((item, index) => {
                const div = document.createElement('div');
                div.className = 'mb-2 small';
                div.innerHTML = `<strong>${index + 1}.</strong> ${item}`;
                dbGeneratedEl.appendChild(div);
            });
        }

        compareResults.style.display = 'block';
    }

    function showError(message) {
        document.getElementById('errorMessage').textContent = message;
        error.style.display = 'block';
    }
});
