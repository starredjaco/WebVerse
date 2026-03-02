from flask import Flask, Response, jsonify

app = Flask(__name__)

FLAG = "WEBVERSE{ssrf_preview_internal_metadata}"


@app.get("/")
def root():
    return Response(
        "metadata service online\nTry /latest/meta-data/\n",
        mimetype="text/plain",
    )


@app.get("/latest/meta-data/")
def latest_root():
    return Response(
        "hostname\niam/\ninstance-id\n",
        mimetype="text/plain",
    )


@app.get("/latest/meta-data/hostname")
def hostname():
    return Response("ip-10-0-0-13.internal\n", mimetype="text/plain")


@app.get("/latest/meta-data/instance-id")
def instance_id():
    return Response("i-webverse-ssrf001\n", mimetype="text/plain")


@app.get("/latest/meta-data/iam/")
def iam_root():
    return Response("security-credentials/\n", mimetype="text/plain")


@app.get("/latest/meta-data/iam/security-credentials/")
def iam_creds_index():
    return Response("webverse-training-role\n", mimetype="text/plain")


@app.get("/latest/meta-data/iam/security-credentials/webverse-training-role")
def iam_creds_role():
    return jsonify(
        {
            "Code": "Success",
            "Type": "AWS-HMAC",
            "AccessKeyId": "ASIAWEBVERSETRAINING",
            "SecretAccessKey": "not-a-real-key",
            "Token": "demo-token",
            "Flag": FLAG,
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
