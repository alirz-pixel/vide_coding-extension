from pathlib import Path
import yaml

BASE_PATH = Path(__file__).parent / "templates"

class PromptBuilder:
    def __init__(self, template_path: str = "teacher.yaml"):
        self._templates = self._load(BASE_PATH / template_path)

    def _load(self, path: str) -> dict:
        with open(Path(path), "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def build_system(self, doc_context: str = "") -> str:
        system = self._templates["system"]

        parts = [system["base"]]

        if doc_context and system.get("doc_context_suffix"):
            suffix = system["doc_context_suffix"].replace("{ doc_context }", doc_context)
            parts.append(suffix)
        if system.get("hard_rule"):
            parts.append(system["hard_rule"])

        return "\n".join(parts)

    def build_message(self, history: list, code: str) -> list[dict]:
        message = []

        for msg in history:
            message.append({"role": msg.role, "content": msg.content})

        # TODO: 모델의 퀄리티가 더 좋아졌을 경우, previous를 사용하기
        # 현재로써 previous code 는 정보량이 너무 많아져 LLM 답변 퀄리티가 낮아짐
        # [PREVIOUS CODE]
        # {req.prev_code}

        message.append({
            "role": "user",
            "content": f"[CURRENT CODE]\n{code}",
        })

        return message


if __name__ == '__main__':
    builder = PromptBuilder("keyword.yaml")

    prompt = builder.build_system("sdf")
    print(prompt)