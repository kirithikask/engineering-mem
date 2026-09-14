import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen3:4b"


def ask_qwen(prompt):

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "think": False
        },
        timeout=180
    )

    response.raise_for_status()

    return response.json()["response"]


if __name__ == "__main__":

    prompt = """
You are an industrial maintenance engineering assistant.

An excavator has weak digging force.

Give exactly 3 possible causes.
Keep the answer short.
"""

    answer = ask_qwen(prompt)

    print("\n===== QWEN RESPONSE =====")
    print(answer)