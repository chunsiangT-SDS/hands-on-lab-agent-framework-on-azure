---
published: true
type: workshop
title: Product Hands-on Lab - Agent Framework on Azure
short_title: Agent Framework on Azure
description: This workshop will cover how to build agentic applications using the Agent Framework on Azure, leveraging various Azure services to create scalable and efficient solutions.
level: beginner # Required. Can be 'beginner', 'intermediate' or 'advanced'
navigation_numbering: false
authors: # Required. You can add as many authors as needed
  - Olivier Mertens
  - David Rei
  - Damien Aicheh
contacts: # Required. Must match the number of authors
  - "@olmertens"
  - "@reidav"
  - "@damienaicheh"
duration_minutes: 300
tags: microsoft foundry, agent framework, ai search, ag-ui, dev-ui, csu, codespace, devcontainer
navigation_levels: 3
banner_url: assets/banner.jpg
audience: developers, architects, AI engineers

---

# Product Hands-on Lab - Agent Framework on Azure

Welcome to this hands-on lab! In this workshop, you will learn how to build agentic applications using the Agent Framework on Azure.

---

## Prerequisites

### 🖥️ Local Development Environment

Before starting this workshop, ensure you have the following tools installed on your machine:

#### Required Tools

| Tool | Description | Installation Link |
|------|-------------|-------------------|
| **Azure CLI** | Command-line interface for Azure | [Install Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) |
| **Terraform** | Infrastructure as Code tool | [Install Terraform on Azure](https://learn.microsoft.com/azure/developer/terraform/quickstart-configure) |
| **Git** | Version control system | [Install Git](https://learn.microsoft.com/devops/develop/git/install-and-set-up-git) |
| **Visual Studio Code** | Code editor | [Download VS Code](https://code.visualstudio.com/download) |

<div class="tip" data-title="Windows Installation">

> You can install these tools using `winget` in PowerShell:
> ```powershell
> winget install -e --id Microsoft.AzureCLI
> winget install -e --id Hashicorp.Terraform
> winget install -e --id Git.Git
> winget install -e --id Microsoft.VisualStudioCode
> ```

</div>

### 🧩 Visual Studio Code Extensions

Install the following extensions in Visual Studio Code:

#### Required Extensions

| Extension | ID | Purpose |
|-----------|-----|---------|
| **GitHub Copilot** | `GitHub.copilot` | AI-assisted coding |
| **GitHub Copilot Chat** | `GitHub.copilot-chat` | Interactive AI chat |
| **HashiCorp Terraform** | `HashiCorp.terraform` | Terraform syntax & IntelliSense |
| **Azure Account** | `ms-vscode.azure-account` | Azure sign-in integration |
| **Azure Tools** | `ms-vscode.vscode-node-azure-pack` | Azure development tools |

#### Recommended Extensions for AI Development

| Extension | ID | Purpose |
|-----------|-----|---------|
| **AI Toolkit** | `ms-windows-ai-studio.windows-ai-studio` | AI model development & testing |
| **Azure MCP Server** | `ms-azuretools.azure-mcp` | Azure Model Context Protocol server |
| **Azure Learn MCP** | `ms-azuretools.vscode-azure-github-copilot` | Azure documentation & best practices |
| **Python** | `ms-python.python` | Python language support |
| **Jupyter** | `ms-toolsai.jupyter` | Jupyter notebook support |
| **Pylance** | `ms-python.vscode-pylance` | Python IntelliSense |

<div class="task" data-title="Install Extensions">

> Install extensions via command line:
> ```powershell
> # Required Extensions
> code --install-extension GitHub.copilot
> code --install-extension GitHub.copilot-chat
> code --install-extension HashiCorp.terraform
> code --install-extension ms-vscode.azure-account
> code --install-extension ms-vscode.vscode-node-azure-pack
> 
> # Recommended AI Extensions
> code --install-extension ms-windows-ai-studio.windows-ai-studio
> code --install-extension ms-azuretools.azure-mcp
> code --install-extension ms-azuretools.vscode-azure-github-copilot
> code --install-extension ms-python.python
> code --install-extension ms-toolsai.jupyter
> code --install-extension ms-python.vscode-pylance
> ```

</div>

### ☁️ Azure Requirements

- An active Azure subscription with **Owner** or **Contributor** role
- Sufficient quota for the following services:
  - Azure AI Foundry
  - Azure AI Search
  - Azure Managed Redis
  - Azure OpenAI models

### ✅ Verification

After installation, verify your setup by running these commands:

```powershell
# Check Azure CLI
az --version

# Check Terraform
terraform --version

# Check Git
git --version

# Login to Azure (replace with your tenant)
az login --tenant <your-tenant-id-or-domain.com>

# Display your account details
az account show
```

<div class="warning" data-title="Important">

> Make sure you are logged into the correct Azure subscription before proceeding with the infrastructure deployment.

</div>

---

### Deploy the Infrastructure

First, you need to initialize the Terraform infrastructure by running the following commands.

### Option 1: Local Environment

Login to your Azure account:

```bash
az login --tenant <yourtenantid or domain.com>
```

### Option 2: GitHub Codespace

You might need to specify `--use-device-code` parameter to ease the Azure CLI authentication process:

```bash
az login --use-device-code --tenant <yourtenantid or domain.com>

# Display your account details
az account show
```

### Set Environment Variables

Set the `ARM_SUBSCRIPTION_ID` environment variable to your Azure subscription ID:

```bash
export ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
```

### Deploy with Terraform

Navigate to the `infra` directory and initialize Terraform:

```bash
cd infra && terraform init
```

Then run the following command to deploy the infrastructure:

```bash
# Apply the deployment directly
terraform apply -auto-approve
```

<div class="info" data-title="Deployment Time">

> The infrastructure deployment may take 15-30 minutes to complete depending on the Azure region and resource availability.

</div>

Scénario : “Helpdesk Ops Assistant”
Tu construis un mini‑helpdesk piloté par agents qui traite des tickets internes avec des FAQ d’entreprise (AI Search), un carnet d’actions IT (MCP server) et des outils natifs.


Agent 1 – Orchestrator : route les requêtes et choisit le bon flux (Solo vs. Group Chat). 
Agent 2 – Complexity Analyst (solo) : analyse le ticket, produit un output structuré (data contract) et propose la stratégie (réponse directe, création de ticket, escalade, docs Learn à citer). 
Agent 3 – Learn Agent (MCP mslearn) : interroge la connaissance via Foundry IQ (et/ou un serveur MCP “mslearn”) pour fournir des citations Learn pertinentes. 
Agent 4 – GitHub Agent (MCP github) : exécute les actions de ticketing GitHub (issue, labels, commentaires), en s’appuyant sur les éléments fournis par les 2 autres agents.

---

## Create your first agent

Let's create a first simple agent using the Agent Framework and a Foundry model to respond to basic queries.

Inside the `src` folder, you will find a `pyproject.toml` file that defines the dependencies for your Python project. Make sure to install them using pip:

```bash
uv sync
```

Then, rename the `.env.template` file to `.env` and update the environment variables with the values from your deployed infrastructure.

To connect to the AI chat model you need, you will use the Microsoft Foundry project resource to connect to the deployed models.

Go to Azure, inside your resource group, select the Microsoft Foundry project: 

IMAGE 

Then select `Go to Foundry portal`: 

IMAGE 

You will be redirected to the home page of Microsoft Foundry Portal where you will have to copy paste the endpoint and assign it's value inside the `.env` file in the `AZURE_AI_PROJECT_ENDPOINT` environment variable. 

When it's done, due to the role`assigned to you on this cloud resource, you can have access to the models with your code. 

Now let's create your first agent! 

Inside `main.py` first load the environment file :

```python
from dotenv import load_dotenv

load_dotenv()
```

Then, create a simple agent using the Agent Framework to analyze an ask.

```python
TODO
```

Let's run the agent with a simple prompt to analyze a first ask:

```python
TODO
```

The final `main.py` file can be found in `solutions/lab_1.py`.

Now, run your agent by opening a terminal and inside the `src` folder:

```bash
uv run python main.py
```

If you try to run the agent multiple times, you might hit the rate limit of tokens per minute. If that happens, you will see a 429 error. Just wait a minute and try again.

Also, if you look at the output, the response is always different because the model is generative and non-deterministic by default, but you ask the model to structure the output in a specific format. That's what you will do in the next step.

To help you build and test your agent more easily, instead of relying only on the console output, let's introduce Dev UI integration.

Let's modify the `main.py` file to add Dev UI integration.

```python
TODO
```

Now if you run your agent again:

```bash
devui main.py
```

The final `main.py` file can be found in `solutions/lab_1_bis.py`.

---

## Add response format

Let's structure the output of your agent to make it more useful.

To make sure the IssueAnalyzerAgent provide the same structure every time, let's define a response format using a basic python class.

Inside the `src` folder, create a new folder called `models` and inside this folder create a new file called `issue_analyzer.py`.

```python
from pydantic import BaseModel
from enum import Enum

class Complexity(Enum):
    NA = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
        
class IssueAnalyzer(BaseModel):
    """Information about an issue."""
    title: str | None = None
    description: str | None = None
    reason: str | None = None
    complexity: Complexity | None = None
    time_estimate_hours: str | None = None
```

As you can see, the `IssueAnalyzer` class defines multiple fields that the agent will fill when answering a prompt.

Now, let's modify the `main.py` file to use this response format. Inside the creation of the agent, add the `response_format` parameter:

```python
TODO
```

You can now run your agent again:

```bash
devui main.py
```

You should notice that the output is now structured according to the `IssueAnalyzer` class you defined.

The final `main.py` file can be found in `solutions/lab_2.py`.

---

## Add native tools

If you looked at the output of your agent, you probably noticed that the estimated time to resolve the issue is randomly generated by the model. To make it more accurate, let's add a native tool that will help the agent estimate the time based on the complexity of the issue.

First, create a new folder called `tools` inside the `src` folder. Then, inside this folder, create a new file called `time_per_issue_tools.py`.

```python
from models.issue_analyzer import Complexity
from typing import Annotated
from pydantic import Field

class TimePerIssueTools:

    def calculate_time_based_on_complexity(
        self,
        complexity: Annotated[Complexity, Field(description="The complexity level of the issue.")],
    ) -> str:
        """Calculate the time required based on issue complexity."""
        match complexity:
            case Complexity.NA:
                return "1 hour"
            case Complexity.LOW:
                return "2 hours"
            case Complexity.MEDIUM:
                return "4 hours"
            case Complexity.HIGH:
                return "8 hours"
            case _:
                return "Unknown complexity level"
```

This class defines a single tool that calculates the estimated time to resolve an issue based on its complexity. Of course, you can implement more tools as needed, with API calls or other logic.

Now, let's modify the `main.py` file to add this tool to your agent inside the agent creation in the `tools` parameter:

```python
TODO
```

Now, run your agent again:

```bash
devui main.py
```

As you can see in the `Tools` tab of Dev UI, the agent used the `calculate_time_based_on_complexity` tool to estimate the time to resolve the issue based on its complexity.

Your IssueAnalyzerAgent is now more precise and reliable!

The final `main.py` file can be found in `solutions/lab_3.py`.

---

## Add MCP tool

You have now a first agent to analyze issues and request of users, but to build a complete helpdesk solution, you need to add another agent responsible of adding the query as a ticket. For the purpose of this workshop, you will use your own GitHub repository as a ticketing system, using GitHub Issues.

To do that, you will use the MCP GitHub tool provided by GitHub and create a new agent called GitHubAgent.

### Get a GitHub PAT (Personal Access Token)

To authenticate to GitHub, you need to create a Personal Access Token (PAT) with the appropriate permissions. This PAT will only need to have access to your repository (result of the fork you did at the beginning of the workshop) and read/write access to issues.

To do so, go to your GitHub account settings, then to **Developer Settings** > **Personal Access Tokens** > **Fine-grained tokens** and create a new token with the following settings:

- Give it a name, e.g., `Agent Framework Workshop Token`
- Set the expiration to `30 days`
- Under **Repository access**, select `Only select repositories` and choose the repository you forked
- Under **Permissions**, set the following:
  - Issues: `Read and write`

Once the token is created, make sure to copy it and paste it inside the `.env` file in the `GITHUB_PAT` environment variable. Also, set the `GITHUB_REPOSITORY` environment variable to the format `owner/repo`, e.g., `your-username/your-forked-repo`.

### Create the GitHubAgent

Now, let's create the GitHubAgent inside the `main.py` file. Just after the creation of the IssueAnalyzerAgent, add the following code:

```python
TODO
```

As you can see, you dynamically load the MCP GitHub tool, pass the authentication parameters, and create the agent using this tool.

To test the GitHubAgent, update the Dev UI setup to run the GitHubAgent instead of the IssueAnalyzerAgent:

```python
TODO
```

Now, run your agent again:

```bash
devui main.py
```

If you ask the agent to create a ticket, it should create a new issue in your GitHub repository!

IMAGE

The final `main.py` file can be found in `solutions/lab_4.py`.

---

## Create a group chat workflow

You have now two agents: the IssueAnalyzerAgent to analyze issues and the GitHubAgent to create tickets in GitHub. To build a complete helpdesk solution, you need to orchestrate these two agents to work together in a group chat. 

To do that you will use a mechanism called Group Chat Workflow provided by the Agent Framework.

This will allow the agents to communicate and collaborate to handle ask in their own chat.

Let's create the `GroupChatBuilder` inside the `main.py` file. Just after the creation of the GitHubAgent, add the following code:

```python
TODO
```

As you can see, you create a group chat workflow with the IssueAnalyzerAgent and the GitHubAgent. 
As you can see, the agents are guided by a manager agent that will route the requests to the appropriate agent based on the prompt.

Now, update the Dev UI setup to run the group chat workflow instead of the individual agents:

```python
TODO
```

Now, run your agent again:

```bash
devui main.py
```

You can now interact with the group chat workflow. The manager agent will route your requests to the appropriate agent based on the prompt.

The final `main.py` file can be found in `solutions/lab_5.py`.

---

## Orchestrate with a sequencial workflow

Let's go a step further and add one more agent in the picture. You will add an MSLearnAgent that will provide relevant documentation from Microsoft Learn to help the agents answer user requests. This agent will use the MCP Learn tool.

First, create the MSLearnAgent inside the `main.py` file. Just after the creation of the GitHubAgent, add the following code:

```python
TODO
```

As you can see, you dynamically load the MCP Learn tool, without authentication for this one, as it's totally open, and create the agent using this tool.

Then, let's create a sequential workflow that will first, call the MSLearnAgent and then the group of agents containing the IssueAnalyzerAgent and the GitHubAgent.

Let's first transform the workflow containing the IssueAnalyzerAgent and the GitHubAgent into an agent so it can be called inside another workflow.

```python
TODO
```

Then, create the sequential workflow:

```python
TODO
```

Update the Dev UI setup to run the sequential workflow instead of the group chat workflow:

```python
TODO
```

Finally, run your agent again:

```bash
devui main.py
```

The final `main.py` file can be found in `solutions/lab_6.py`.

---

## Add your own knowledge base with RAG

You now have a complete helpdesk solution with multiple agents working together to handle user requests. However, the GitHubAgent is doing some ticketing without really knowing your company's conventions and best practices. To improve this, you will add another source of knowledge using Retrieval-Augmented Generation (RAG) with Azure AI Search.

Let's create an index of data using the provided script `docs_indexer.py` inside the `data` folder. This script will read all the files inside the `data/docs` folder and index them into your Azure AI Search service. This will be used as a knowledge base for the GitHubAgent.

First, make sure to set the `AZURE_AI_SEARCH_ENDPOINT` environment variables in your `.env` file with the values from your deployed infrastructure.

Then, run the indexer script:

```bash
python data/docs_indexer.py
```

Now, let's modify the GitHubAgent to use this knowledge base when answering user requests. Inside the creation of the GitHubAgent, add the following code to create a retriever using Azure AI Search:

```python
TODO
```

Then, pass this retriever to the GitHubAgent:

```python
TODO
```

You can run the flow again, and now the GitHubAgent will use the knowledge base to provide more accurate and relevant answers based on your company's documentation.


---

## Add observability with OpenTelemetry

---

## Evaluate your agent

---

## Add AG UI integration

---

## Bonus: Agent-to-Agent Communication