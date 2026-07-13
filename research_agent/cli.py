from __future__ import annotations

import argparse
import json

from research_agent.chat import ResearchChatAgent, run_terminal
from research_agent.logging import ModelCallLogger
from research_agent.tools.llm_client import ModelGateway


def main() -> None:
    parser = argparse.ArgumentParser(description="Research Agent ReAct CLI.")
    sub = parser.add_subparsers(dest="command", required=True)
    chat = sub.add_parser("chat", help="Start the persistent ReAct terminal agent.")
    chat.add_argument("--session", default="")
    chat.add_argument("--new", action="store_true")
    chat.add_argument("--message", action="append", dest="messages", default=[])
    sub.add_parser("config", help="Show non-secret effective project configuration.")
    sub.add_parser("model-health", help="Make one short explicit model health request.")
    args = parser.parse_args()
    agent = ResearchChatAgent()
    if args.command == "config":
        cfg = agent.config
        print(json.dumps({"llm_provider": cfg.llm_provider, "llm_model": cfg.llm_model, "llm_base_url": cfg.llm_base_url, "llm_configured": cfg.llm_configured, "timeout_seconds": cfg.llm_timeout_seconds}, ensure_ascii=False, indent=2))
        return
    if args.command == "model-health":
        session = agent.new_session()
        print(json.dumps(ModelGateway(agent.config, ModelCallLogger(agent.sessions.directory(session.session_id))).health(), ensure_ascii=False, indent=2))
        return
    if not args.messages:
        run_terminal(session_id=args.session, resume_latest=not args.new)
        return
    session = agent.load_or_create(args.session, resume_latest=not args.new)
    for message in args.messages:
        response = agent.handle(session, message, progress=lambda event, skill: print(f"[{event}] {skill}", flush=True))
        session = response.session
        print(response.message, flush=True)
    print(json.dumps({"session_id": session.session_id, "artifacts": session.artifacts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
