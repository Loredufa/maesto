
import os
import re
from datetime import datetime

from openai import OpenAI
from rich.console import Console
from rich.panel import Panel


# Define the read_file function
def read_file(file_path):
    try:
        with open(file_path, 'r') as file:
            content = file.read()
        return content
    except FileNotFoundError:
        print(f"Error: The file at {file_path} was not found.")
        return None
    except Exception as e:
        print(f"An error occurred while reading the file: {e}")
        return None
    
# Initialize OpenAI API client
openai_client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key="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")

# Available Granite model 
GRANITE_MODEL = "ibm/granite-34b-code-instruct"

# Initialize the Rich Console 
# Esto crea un objeto Console de la biblioteca Rich, que se usa para imprimir texto formateado en la consola.
console = Console()

#Maneja la orquestación de tareas. / Formatea y envía mensajes al modelo Granite.
def granite_orchestrator(objective, file_content=None, previous_results=None, use_search=False):
    console.print(f"\n[bold]Calling Orchestrator for your objective[/bold]")
    previous_results_text = "\n".join(previous_results) if previous_results else "None"
    if file_content:
        console.print(Panel(f"File content:\n{file_content}", title="[bold blue]File Content[/bold blue]", title_align="left", border_style="blue"))
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": f"Based on the following objective{' and file content' if file_content else ''}, and the previous sub-task results (if any), please break down the objective into the next sub-task, and create a concise and detailed prompt for a subagent so it can execute that task. IMPORTANT!!! when dealing with code tasks make sure you check the code for errors and provide fixes and support as part of the next sub-task. If you find any bugs or have suggestions for better code, please include them in the next sub-task prompt. Please assess if the objective has been fully achieved. If the previous sub-task results comprehensively address all aspects of the objective, include the phrase 'The task is complete:' at the beginning of your response. If the objective is not yet fully achieved, break it down into the next sub-task and create a concise and detailed prompt for a subagent to execute that task.:\n\nObjective: {objective}" + ('\nFile content:\n' + file_content if file_content else '') + f"\n\nPrevious sub-task results:\n{previous_results_text}"}
    ]

    granite_response = openai_client.chat.completions.create(
        model=GRANITE_MODEL,
        messages=messages,
        max_tokens=2048
    )

    response_text = granite_response.choices[0].message.content
    usage = granite_response.usage

    console.print(Panel(response_text, title=f"[bold green]Granite Orchestrator[/bold green]", title_align="left", border_style="green", subtitle="Sending task to Granite 👇"))
    console.print(f"Input Tokens: {usage.prompt_tokens}, Output Tokens: {usage.completion_tokens}, Total Tokens: {usage.total_tokens}")

    return response_text, file_content
#Maneja subtareas específicas.
def granite_sub_agent(prompt, previous_granite_tasks=None, continuation=False):
    if previous_granite_tasks is None:
        previous_granite_tasks = []

    continuation_prompt = "Continuing from the previous answer, please complete the response."
    system_message = "Previous Granite tasks:\n" + "\n".join(f"Task: {task['task']}\nResult: {task['result']}" for task in previous_granite_tasks)
    if continuation:
        prompt = continuation_prompt

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": prompt}
    ]

    granite_response = openai_client.chat.completions.create(
        model=GRANITE_MODEL,
        messages=messages,
        max_tokens=2048
    )

    response_text = granite_response.choices[0].message.content
    usage = granite_response.usage

    console.print(Panel(response_text, title="[bold blue]Granite Sub-agent Result[/bold blue]", title_align="left", border_style="blue", subtitle="Task completed, sending result to Granite 👇"))
    console.print(f"Input Tokens: {usage.prompt_tokens}, Output Tokens: {usage.completion_tokens}, Total Tokens: {usage.total_tokens}")

    if usage.completion_tokens >= 2048:  # Threshold set to 4000 as a precaution
        console.print("[bold yellow]Warning:[/bold yellow] Output may be truncated. Attempting to continue the response.")
        continuation_response_text = granite_sub_agent(prompt, previous_granite_tasks, continuation=True)
        response_text += continuation_response_text

    return response_text
#Refina los resultados de las subtareas en una salida final. / Genera estructura de carpetas y código si es un proyecto de programación.
def granite_refine(objective, sub_task_results, filename, projectname):
    console.print("\nCalling Granite to provide the refined final output for your objective:")
    messages = [
        {
            "role": "user",
            "content": f"Objective: {objective}\n\nSub-task results:\n" + "\n".join(sub_task_results) + "\n\nPlease review and refine the sub-task results into a cohesive final output. Add any missing information or details as needed. When working on code projects, ONLY AND ONLY IF THE PROJECT IS CLEARLY A CODING ONE please provide the following:\n1. Project Name: Create a concise and appropriate project name that fits the project based on what it's creating. The project name should be no more than 20 characters long.\n2. Folder Structure: Provide the folder structure as a valid JSON object, where each key represents a folder or file, and nested keys represent subfolders. Use null values for files. Ensure the JSON is properly formatted without any syntax errors. Please make sure all keys are enclosed in double quotes, and ensure objects are correctly encapsulated with braces, separating items with commas as necessary.\nWrap the JSON object in <folder_structure> tags.\n3. Code Files: For each code file, include ONLY the file name NEVER EVER USE THE FILE PATH OR ANY OTHER FORMATTING YOU ONLY USE THE FOLLOWING format 'Filename: <filename>' followed by the code block enclosed in triple backticks, with the language identifier after the opening backticks, like this:\n\n```python\n<code>\n```"
        }
    ]

    granite_response = openai_client.chat.completions.create(
        model=GRANITE_MODEL,
        messages=messages,
        max_tokens=4096
    )

    response_text = granite_response.choices[0].message.content
    usage = granite_response.usage

    console.print(f"Input Tokens: {usage.prompt_tokens}, Output Tokens: {usage.completion_tokens}, Total Tokens: {usage.total_tokens}")

    console.print(Panel(response_text, title="[bold green]Final Output[/bold green]", title_align="left", border_style="green"))
    return response_text

# ... (rest of the functions remain the same)

# Main execution
objective = input("Please enter your objective: ")

provide_file = input("Do you want to provide a file path? (y/n): ").lower() == 'y'
#Solicita un objetivo al usuario. / Itera entre el orquestador y el subagente hasta completar la tarea.
if provide_file:
    file_path = input("Please enter the file path: ")
    if os.path.exists(file_path):
        file_content = read_file(file_path)
    else:
        print(f"File not found: {file_path}")
        file_content = None
else:
    file_content = None

task_exchanges = []
granite_tasks = []

while True:
    previous_results = [result for _, result in task_exchanges]
    if not task_exchanges:
        granite_result, file_content_for_granite = granite_orchestrator(objective, file_content, previous_results)
    else:
        granite_result, _ = granite_orchestrator(objective, previous_results=previous_results)

    if "The task is complete:" in granite_result:
        final_output = granite_result.replace("The task is complete:", "").strip()
        break
    else:
        sub_task_prompt = granite_result
        if file_content_for_granite and not granite_tasks:
            sub_task_prompt = f"{sub_task_prompt}\n\nFile content:\n{file_content_for_granite}"
        sub_task_result = granite_sub_agent(sub_task_prompt, granite_tasks)
        granite_tasks.append({"task": sub_task_prompt, "result": sub_task_result})
        task_exchanges.append((sub_task_prompt, sub_task_result))
        file_content_for_granite = None

sanitized_objective = re.sub(r'\W+', '_', objective)
timestamp = datetime.now().strftime("%H-%M-%S")
#Usa granite_refine para generar la salida final.
refined_output = granite_refine(objective, [result for _, result in task_exchanges], timestamp, sanitized_objective)

# ... (rest of the code remains the same)