# aura-k8s-chat

This repository contains the code for a Kubernetes AI Agent that translates natural language prompts into `kubectl` commands. The agent uses a LangGraph-based state machine with multiple nodes to ensure commands are safe before execution.

### Architecture

The application is structured around a few key components:

1.  **LangGraph Agent (`k8s-chat-app.py`)**: The core of the application is a LangGraph agent that processes user requests in a structured way. It consists of four main nodes:

      * **Generator Node**: Translates a user's natural language request into a single `kubectl` command. It is designed to include the `-o json` flag for commands that support it.
      * **Critic Node**: Reviews the generated `kubectl` command against a set of predefined safety rules. The rules are loaded from a file named `critic_rules.txt`.
      * **Execution Node**: Executes the `kubectl` command only after it has been approved by the critic.
      * **Summarizer Node**: Summarizes the output of the `kubectl` command into a human-readable format.

2.  **Safety Rules (`critic_rules.txt`)**: A `ConfigMap` (`k8s/03-configmap.yml`) defines the safety rules for the agent, which are mounted into the container at `/app/critic_rules.txt`. The rules strictly limit the allowed actions to `get`, `describe`, and `logs`. Forbidden actions include `delete`, `apply`, `exec`, `edit`, `create`, or `rollout`. The rules also prohibit the use of shell operators like `;`, `&&`, `||`, `|`, `>`, `<`, or `     ` \`.

3.  **Kubernetes Manifests (`k8s/` directory)**: The application is deployed on Kubernetes using a set of YAML files that configure its resources:

      * `00-service-account.yml`: Creates a dedicated ServiceAccount for the agent.
      * `01-role.yml`: Defines a `pod-reader-role` with permissions to `get`, `list`, `watch`, and `describe` pods and pod logs.
      * `02-role-binding.yml`: Binds the `pod-reader-role` to the `k8s-agent-sa` ServiceAccount.
      * `03-configmap.yml`: Creates a `ConfigMap` to store the critic safety rules.
      * `04-deployment.yml`: Defines the `Deployment` for the application, including the container image, readiness/liveness probes, and resource requests/limits. It also mounts the `ConfigMap` containing the critic rules.
      * `05-service.yml`: Exposes the application as a Kubernetes `Service` on port 80.
      * `06-hpa.yml`: Configures a `HorizontalPodAutoscaler` to manage the number of replicas based on CPU and memory utilization.
      * `07-network-policy.yml`: Applies a `NetworkPolicy` to deny all ingress traffic and allow egress traffic for DNS and general internet access.

4.  **Containerization and CI/CD**:

      * **Dockerfile**: The application is containerized using a multi-stage `Dockerfile`. It builds a virtual environment with required dependencies (`langgraph`, `boto3`, `fastapi`, etc.) and installs `kubectl`.
      * **GitHub Actions Workflow**: The `.github/workflows/build-and-push.yml` file defines a workflow that automatically builds the Docker image and pushes it to the GitHub Container Registry (GHCR) on every push to the `main` branch.

### Dependencies

The Python dependencies for the application are listed in `requirements.txt`.

### Usage

The application exposes a single API endpoint:

  * **`POST /invoke`**: Accepts a JSON payload with a `user_prompt` and returns a summary of the `kubectl` command execution.

You can interact with the API using a tool like `curl` after deployment:

```bash
curl -X POST http://<your-service-ip>/invoke \
-H "Content-Type: application/json" \
-d '{"user_prompt": "list the pods in the default namespace"}'
```