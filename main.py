import json
import sys
from app.pipeline import process_message
from tests.test_cases import GIVEN_MESSAGES, ADDITIONAL_MESSAGES


def print_decision(i: int, decision) -> None:
    print(f"\n{'=' * 90}")
    print(f"[{i}] MESSAGE: {decision.message}")
    print(f"{'-' * 90}")
    print(json.dumps(json.loads(decision.model_dump_json()), indent=2, ensure_ascii=False))


def main() -> None:
    if len(sys.argv) > 1:
        message = " ".join(sys.argv[1:])
        decision = process_message(message)
        print_decision(1, decision)
        return

    print("### GIVEN TEST MESSAGES (from the task) ###")
    for i, msg in enumerate(GIVEN_MESSAGES, 1):
        print_decision(i, process_message(msg))

    print("\n\n### ADDITIONAL TEST MESSAGES (written for this submission) ###")
    for i, msg in enumerate(ADDITIONAL_MESSAGES, 1):
        print_decision(i, process_message(msg))


if __name__ == "__main__":
    main()
