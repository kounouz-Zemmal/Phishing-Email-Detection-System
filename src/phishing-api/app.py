"""
PhishGuard — Flask Backend
Endpoints:
  GET  /              → serves the HTML UI
  POST /analyze       → single email prediction (manual entry)
  POST /predict_eml   → .eml file upload prediction
"""

import os
import re
import sys
import logging
import numpy as np
import pandas as pd
import joblib
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from urllib.parse import urlparse
from sklearn.base import BaseEstimator, TransformerMixin

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# ── Custom transformers — must match exactly what was used during training ─────
class ColumnSelector(BaseEstimator, TransformerMixin):
    def __init__(self, column):
        self.column = column
    def fit(self, X, y=None):
        return self
    def transform(self, X):
        return X[self.column].fillna('')

class NumericSelector(BaseEstimator, TransformerMixin):
    def __init__(self, columns):
        self.columns = columns
    def fit(self, X, y=None):
        return self
    def transform(self, X):
        return X[self.columns].values


# ── Domain helpers ────────────────────────────────────────────────────────────
def extract_email_domain(email_str) -> str:
    if not isinstance(email_str, str):
        return ''
    email_str = email_str.strip().lower()
    if not email_str or '@' not in email_str:
        return ''
    local_part, domain = email_str.rsplit('@', 1)
    domain = domain.strip().strip('.')
    if not local_part or not domain or ' ' in domain:
        return ''
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*', domain):
        return ''
    return domain


def extract_url_domain(url) -> str:
    if not isinstance(url, str):
        return ''
    url = url.strip().lower()
    if not url:
        return ''
    if url.startswith('//'):
        url = 'https:' + url
    elif '://' not in url:
        url = 'https://' + url
    try:
        parsed = urlparse(url)
    except Exception:
        return ''
    host = (parsed.netloc or parsed.path.split('/')[0]).strip()
    host = host.split('@')[-1].split(':')[0].strip().strip('.')
    if not host or ' ' in host:
        return ''
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*', host):
        return ''
    return host


# ── Feature engineering — must mirror notebook ────────────────────────────────
def engineer_features(data) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        df = data.copy()
    else:
        df = pd.DataFrame([data])

    for col in ['subject', 'body_clean', 'from_email', 'to_email', 'urls']:
        if col in df.columns:
            df[col] = df[col].fillna('')
        else:
            df[col] = ''

    for col in ['url_count', 'has_ip_url', 'char_count', 'word_count', 'html_flag']:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    df['from_domain']   = df['from_email'].apply(extract_email_domain)
    df['to_domain']     = df['to_email'].apply(extract_email_domain)
    df['same_domain']   = ((df['from_domain'] != '') & (df['from_domain'] == df['to_domain'])).astype(int)
    df['is_edu_domain'] = df['from_domain'].str.contains(r'\.(?:edu|dz)(?:\.|$)', regex=True).fillna(False).astype(int)

    raw_urls    = str(df.at[0, 'urls'])
    url_tokens  = [u.strip() for u in re.split(r'\s*,\s*', raw_urls) if u.strip()]
    url_domains = [d for d in (extract_url_domain(u) for u in url_tokens) if d]
    df['url_is_edu']          = int(any(re.search(r'\.(?:edu|dz)(?:\.|$)', d) for d in url_domains))
    df['url_domain_mismatch'] = int(
        bool(df.at[0, 'from_domain']) and any(d != df.at[0, 'from_domain'] for d in url_domains)
    )

    # ── Display name vs. sender domain mismatch ──
    BRAND_DOMAINS = {
        'paypal':    ['paypal.com'],
        'amazon':    ['amazon.com', 'amazon.co.uk', 'amazonses.com'],
        'microsoft': ['microsoft.com', 'outlook.com', 'hotmail.com', 'live.com'],
        'google':    ['google.com', 'gmail.com'],
        'apple':     ['apple.com', 'icloud.com'],
        'netflix':   ['netflix.com'],
        'dhl':       ['dhl.com'],
        'fedex':     ['fedex.com'],
        'ups':       ['ups.com'],
    }
    def _display_name_mismatch(from_field: str, actual_domain: str) -> int:
        if not isinstance(from_field, str) or not actual_domain:
            return 0
        name_part = from_field.lower()
        for brand, legit_domains in BRAND_DOMAINS.items():
            if brand in name_part:
                if not any(actual_domain == d or actual_domain.endswith('.' + d)
                           for d in legit_domains):
                    return 1
        return 0
    df['display_name_mismatch'] = _display_name_mismatch(
        df.at[0, 'from_email'], df.at[0, 'from_domain']
    )

    # ── Lookalike / typosquatting domain detection ──
    _KNOWN_LEGIT = ['paypal.com', 'amazon.com', 'microsoft.com', 'google.com',
                    'apple.com', 'netflix.com', 'dhl.com', 'fedex.com', 'ups.com']

    def _lev_distance(a: str, b: str) -> int:
        if a == b:
            return 0
        if not a:
            return len(b)
        if not b:
            return len(a)

        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a, start=1):
            curr = [i]
            for j, cb in enumerate(b, start=1):
                cost = 0 if ca == cb else 1
                curr.append(min(
                    prev[j] + 1,      # deletion
                    curr[j - 1] + 1,  # insertion
                    prev[j - 1] + cost  # substitution
                ))
            prev = curr
        return prev[-1]

    def _is_lookalike(domain: str, threshold: int = 2) -> int:
        if not domain:
            return 0
        parts = domain.split('.')
        if len(parts) < 2:
            return 0
        apex = '.'.join(parts[-2:])
        for legit in _KNOWN_LEGIT:
            if apex == legit:
                return 0
            if _lev_distance(apex, legit) <= threshold:
                return 1
        return 0

    df['lookalike_domain'] = _is_lookalike(df.at[0, 'from_domain'])

    # ── Reply-To vs From domain mismatch ──
    if 'reply_to' in df.columns:
        df['reply_to'] = df['reply_to'].fillna('')
        reply_to_domain = extract_email_domain(str(df.at[0, 'reply_to']))
        df['replyto_mismatch'] = int(
            bool(df.at[0, 'from_domain']) and
            bool(reply_to_domain) and
            df.at[0, 'from_domain'] != reply_to_domain
        )
    else:
        df['replyto_mismatch'] = 0

    df['text_combined']      = df['subject'].str.lower() + ' ' + df['body_clean'].str.lower()
    df['subject_len']        = df['subject'].str.len()
    df['subject_excl']       = df['subject'].str.count('!')
    df['subject_caps_ratio'] = df['subject'].apply(lambda s: sum(c.isupper() for c in s) / max(len(s), 1))
    df['body_excl_count']    = df['body_clean'].str.count('!')
    df['body_dollar_count']  = df['body_clean'].str.count(r'\$')

    body_text       = df['body_clean'].str.lower()
    urgent_hits     = body_text.str.count(r'\b(urgent|verify|suspend|click|password|login|free|winner)\b')
    credential_hits = body_text.str.count(
        r'\b(verify|update|secure|unlock)\s+(?:your\s+)?account\b'
        r'|\b(account|password)\s+(?:has|was)\s+(?:been\s+)?(?:suspended|locked|compromised)\b'
    )
    df['body_urgent_words'] = urgent_hits + credential_hits
    df['ip_url_ratio']      = df['has_ip_url'] / df['url_count'].clip(lower=1)
    df['log_char_count']    = np.log1p(df['char_count'])
    df['log_word_count']    = np.log1p(df['word_count'])
    df['log_url_count']     = np.log1p(df['url_count'])

    return df


# ── Register all training-time symbols in __main__ BEFORE joblib.load ─────────
# joblib resolves pickled function/class references by (module, qualname).
# The model was trained in a notebook where everything lived in __main__,
# so we must expose the same names here before deserialising the pickle.
_main = sys.modules['__main__']
_main.engineer_features    = engineer_features
_main.extract_email_domain = extract_email_domain
_main.extract_url_domain   = extract_url_domain
_main.ColumnSelector       = ColumnSelector
_main.NumericSelector      = NumericSelector

# ── Load model artifacts ──────────────────────────────────────────────────────
model     = joblib.load('phishing_model.pkl')
threshold = joblib.load('threshold.pkl')
logger.info(f'Model loaded — threshold: {threshold:.4f}')


# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)


def format_prediction(prob: float) -> dict:
    is_phishing = bool(prob >= threshold)
    label       = 'phishing' if is_phishing else 'legitimate'
    confidence  = prob if is_phishing else 1 - prob
    risk        = 'high' if prob >= 0.8 else 'medium' if prob >= float(threshold) else 'low'
    return {
        'label':                label,
        'phishing_probability': round(float(prob), 4),
        'confidence':           round(float(confidence), 4),
        'risk_level':           risk,
        'threshold':            round(float(threshold), 4),
    }


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


@app.route('/favicon.ico', methods=['GET'])
def favicon():
    return '', 204


@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({'error': 'Empty or invalid JSON body'}), 400
        if 'body' not in data and 'subject' not in data:
            return jsonify({'error': 'At least one of "body" or "subject" is required'}), 400

        body     = data.get('body', '')
        row_data = {
            'subject':    data.get('subject', ''),
            'from_email': data.get('from_email', ''),
            'to_email':   data.get('to_email', ''),
            'reply_to':   data.get('reply_to', ''),
            'body_clean': body,
            'urls':       str(data.get('urls', '[]')),
            'url_count':  int(data.get('url_count', 0)),
            'char_count': int(data.get('char_count', len(body))),
            'word_count': int(data.get('word_count', len(body.split()))),
            'has_ip_url': int(data.get('has_ip_url', 0)),
            'html_flag':  int(data.get('html_flag', 0)),
        }

        df   = engineer_features(row_data)
        prob = model.predict_proba(df)[0][1]
        return jsonify({'prediction': format_prediction(prob)})

    except Exception as e:
        logger.exception('Analyze error')
        return jsonify({'error': str(e)}), 500


@app.route('/predict_eml', methods=['POST'])
def predict_eml():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        f = request.files['file']
        if not f or not f.filename:
            return jsonify({'error': 'No file selected'}), 400
        if not f.filename.lower().endswith('.eml'):
            return jsonify({'error': 'Only .eml files are supported'}), 400

        from eml_parser import parse_eml
        raw_features = parse_eml(f.read())
        logger.info(f'EML parsed: subject="{raw_features["subject"][:60]}"')

        df   = engineer_features(pd.DataFrame([raw_features]))
        prob = model.predict_proba(df)[0][1]
        pred = format_prediction(prob)

        return jsonify({
            'status': 'success',
            'extracted': {
                'subject':              raw_features['subject'][:100],
                'from':                 raw_features['from_email'],
                'to':                   raw_features['to_email'],
                'reply_to':             raw_features['reply_to'],
                'url_count':            raw_features['url_count'],
                'has_ip_url':           bool(raw_features['has_ip_url']),
                'html_flag':            bool(raw_features['html_flag']),
            },
            'prediction': pred,
        })

    except ValueError as e:
        return jsonify({'error': f'Failed to parse EML: {str(e)}'}), 400
    except Exception as e:
        logger.exception('EML predict error')
        return jsonify({'error': str(e)}), 500


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 5004))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)