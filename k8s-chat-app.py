# k8s-chat-app.py

#!/usr/bin/env python3

# # 1. Preamble and Imports
import json
import os  # <-- Add this import
import shlex
import subprocess
import sys
from pathlib import Path
from typing import TypedDict, Dict, Any

import boto3
from langchain_aws import ChatBedrock
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

# # 2. AWS Bedrock LLM Client
try:
    llm = ChatBedrock(
        model_id="anthropic.claude-3-haiku-20240307-v1:0",
        client=boto3.client(service_name="bedrock-runtime", region_name="us-east-1"),
        model_kwargs={"temperature": 0.1},
    )
except Exception as e:
    print(f"Error initializing Bedrock client: {e}")
    print("Please ensure your AWS credentials and region are configured correctly.")
    sys.exit(1)


# # 3. Graph State Definition
class AgentState(TypedDict):
    """
    Defines the state of the LangGraph agent.
    """
    user_prompt: str
    generated_command: str
    critique_result: Dict[str, Any]
    execution_result: str
    final_summary: str


# # 4. The Agent Nodes

# ## A. Generator Node
def generate_command(state: AgentState) -> Dict[str, str]:
    """
    Generates a kubectl command from the user's natural language prompt.
    """
    print(">>> Generating command...")
    user_prompt = state["user_prompt"]

    prompt_template = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are an expert Kubernetes administrator. Your sole purpose is to "
                    "translate a user's natural language request into a single, valid `kubectl` command. "
                    "For commands that support it (like 'get' and 'describe'), you MUST use the '-o json' flag. "
                    "For commands that do not support it (like 'logs'), you MUST NOT use the '-o json' flag. "
                    "Do not provide any explanation, preamble, or markdown formatting. "
                    "Respond with ONLY the command."
                ),
            ),
            ("human", "Request: {user_prompt}"),
        ]
    )

    chain = prompt_template | llm
    response = chain.invoke({"user_prompt": user_prompt})
    generated_command = response.content.strip()

    print(f"    Generated: {generated_command}")
    return {"generated_command": generated_command}


# ## B. Critic Node
def critique_command(state: AgentState) -> Dict[str, Dict[str, Any]]:
    """
    Critiques the generated command against a set of safety rules.
    """
    print(">>> Critiquing command...")
    command = state["generated_command"]
    rules_path = Path("critic_rules.txt")

    try:
        with open(rules_path, "r") as f:
            rules = f.read()
    except FileNotFoundError:
        print(f"    ERROR: critic_rules.txt not found.")
        return {
            "critique_result": {
                "decision": "unsafe",
                "reason": "Safety rules file 'critic_rules.txt' was not found.",
            }
        }

    prompt_template = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are a Kubernetes security auditor. Your task is to review a proposed "
                    "`kubectl` command against a set of safety rules. "
                    "Your response must be a single, valid JSON object with two keys: "
                    "'decision' (either 'safe' or 'unsafe') and 'reason' (a brief explanation if unsafe). "
                    "Do not provide any other text or explanation."
                    "\n\nHere are the rules:\n{rules}"
                ),
            ),
            ("human", "Command to review: {command}"),
        ]
    )

    chain = prompt_template | llm
    response = chain.invoke({"rules": rules, "command": command})
    critique_json_str = response.content

    try:
        critique_result = json.loads(critique_json_str)
    except json.JSONDecodeError:
        print(f"    ERROR: Critic LLM returned malformed JSON: {critique_json_str}")
        critique_result = {
            "decision": "unsafe",
            "reason": "The critic agent returned a malformed response.",
        }

    print(f"    Critique: {critique_result}")
    return {"critique_result": critique_result}


# ## C. Execution Node
def execute_command(state: AgentState) -> Dict[str, str]:
    """
    Executes the kubectl command after it has been approved by the critic.
    """
    print(">>> Executing command...")
    command = state["generated_command"]

    try:
        command_parts = shlex.split(command)
        if command_parts[0] != "kubectl":
             return {"execution_result": "Error: Command must start with 'kubectl'."}

        result = subprocess.run(
            command_parts, capture_output=True, text=True, check=False
        )

        if result.returncode != 0:
            output = f"Error executing command:\n{result.stderr}"
        else:
            output = result.stdout

    except Exception as e:
        output = f"An unexpected error occurred during execution: {e}"

    print(f"    Execution result captured (first 100 chars): {output[:100].strip()}...")
    return {"execution_result": output}


# ## D. Summarizer Node
def summarize_results(state: AgentState) -> Dict[str, str]:
    """
    Summarizes the output from kubectl into a human-readable format.
    """
    print(">>> Summarizing results...")
    execution_result = state["execution_result"]

    if execution_result.strip().lower().startswith("error"):
        print("    Execution resulted in an error. No summary needed.")
        return {"final_summary": f"The command failed to execute.\nDetails: {execution_result}"}

    # This prompt now works for both structured JSON and unstructured text like logs.
    prompt_template = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a helpful assistant. Your task is to summarize the results of a `kubectl` command. "
                "The user has received the following output. Please provide a clear, concise, "
                "and human-readable summary. If the output is a log, present the key information from the log."
            ),
            ("human", "kubectl output:\n{output}"),
        ]
    )

    chain = prompt_template | llm
    response = chain.invoke({"output": execution_result})
    summary = response.content

    print("    Summary generated.")
    return {"final_summary": summary}


# ## E. Report Issue Node
def report_issue(state: AgentState) -> Dict[str, str]:
    """
    Formats the final message when the critic rejects a command.
    """
    print(">>> Reporting issue...")
    critique = state["critique_result"]
    reason = critique.get("reason", "No reason provided.")
    message = f"Execution was halted for safety.\nReason: {reason}"

    return {"final_summary": message}


# # 5. Conditional Routing
def route_after_critique(state: AgentState) -> str:
    """
    Routes to execution or issue reporting based on the critic's decision.
    """
    print(">>> Routing after critique...")
    decision = state["critique_result"].get("decision", "unsafe")

    if decision == "safe":
        print("    Decision: SAFE. Proceeding to execution.")
        return "execute_command"
    else:
        print("    Decision: UNSAFE. Halting execution and reporting issue.")
        return "report_issue"


# # 6. Graph Assembly and Compilation
workflow = StateGraph(AgentState)

workflow.add_node("generate_command", generate_command)
workflow.add_node("critique_command", critique_command)
workflow.add_node("execute_command", execute_command)
workflow.add_node("summarize_results", summarize_results)
workflow.add_node("report_issue", report_issue)

workflow.set_entry_point("generate_command")

workflow.add_edge("generate_command", "critique_command")
workflow.add_conditional_edges(
    "critique_command",
    route_after_critique,
    {"execute_command": "execute_command", "report_issue": "report_issue"},
)
workflow.add_edge("execute_command", "summarize_results")
workflow.add_edge("summarize_results", END)
workflow.add_edge("report_issue", END)

app = workflow.compile()


# # 7. Interactive CLI Main Loop
if __name__ == "__main__":
    print("Kubernetes AI Agent Initialized ✨")
    print("Enter your query below. Type 'exit' or 'quit' to end the session.")

    # Create critic rules file if it doesn't exist
    rules_path = Path("critic_rules.txt")
    if not rules_path.exists():
        rules_content = (
            "1. The command must start with 'kubectl'.\n"
            "2. The allowed actions are 'get', 'describe', and 'logs'. Any other action "
            "(like 'delete', 'apply', 'exec', 'edit', 'create', 'rollout') is strictly forbidden.\n"
            "3. For commands that support it (like 'get' and 'describe'), the command should include the '-o json' output flag.\n"
            "4. The command must not contain any shell operators like ';', '&&', '||', '|', '>', '<', or '`'. "
            "It must be a single, standalone command.\n"
        )
        with open(rules_path, "w") as f:
            f.write(rules_content)
        print("✅ `critic_rules.txt` has been created.")

    # Start the interactive loop
    try:
        while True:
            # Get user input from the prompt
            user_query = input("\nk8s-agent> ")

            # Check for exit commands
            if user_query.lower() in ["exit", "quit"]:
                break

            # Skip empty input
            if not user_query.strip():
                continue

            print("\n🚀 Processing your query...")
            print("-" * 40)
            
            # Invoke the graph with the user's query
            inputs = {"user_prompt": user_query}
            final_state = app.invoke(inputs)

            print("-" * 40)
            print("🏁 Final Response:\n")
            print(final_state.get("final_summary", "No summary was generated."))

    except KeyboardInterrupt:
        print("\nExiting agent...")
    
    print("Goodbye! 👋")