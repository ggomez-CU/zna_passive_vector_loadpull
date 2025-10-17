import subprocess

# Define the paths to your Python scripts
script_path = '.\\src\\MMIC_driveupbiascoupledline.py'
file1_path = r"C:\Users\grgo8200\Documents\GitHub\summer2025_loadpull_repo\data\PA_Spring2023\coupledlinephasefrommmic1.json"
file2_path = r"C:\Users\grgo8200\Documents\GitHub\summer2025_loadpull_repo\data\PA_Spring2023\coupledlinephasefrommmic2.json"
file3_path = r"C:\Users\grgo8200\Documents\GitHub\summer2025_loadpull_repo\data\PA_Spring2023\coupledlinephasefrommmic3.json"
file4_path = r"C:\Users\grgo8200\Documents\GitHub\summer2025_loadpull_repo\data\PA_Spring2023\coupledlinephasefrommmic4.json"
file5_path = r"C:\Users\grgo8200\Documents\GitHub\summer2025_loadpull_repo\data\PA_Spring2023\coupledlinephasefrommmic5.json"


print(f"Running {script_path}...")
result1 = subprocess.run(["python", script_path, "-o", "-i", "-p","-v","-f", file1_path], capture_output=True, text=True)
print(f"Output of {script_path}:\n{result1.stdout}")
if result1.stderr:
    print(f"Errors from {script_path}:\n{result1.stderr}")

print(f"Running {script_path}...")
result1 = subprocess.run(["python", script_path, "-o", "-i", "-p","-v","-f", file2_path], capture_output=True, text=True)
print(f"Output of {script_path}:\n{result1.stdout}")
if result1.stderr:
    print(f"Errors from {script_path}:\n{result1.stderr}")

print(f"Running {script_path}...")
result1 = subprocess.run(["python", script_path, "-o", "-i", "-p","-v","-f", file3_path], capture_output=True, text=True)
print(f"Output of {script_path}:\n{result1.stdout}")
if result1.stderr:
    print(f"Errors from {script_path}:\n{result1.stderr}")

print(f"Running {script_path}...")
result1 = subprocess.run(["python", script_path, "-o", "-i", "-p","-v","-f", file4_path], capture_output=True, text=True)
print(f"Output of {script_path}:\n{result1.stdout}")
if result1.stderr:
    print(f"Errors from {script_path}:\n{result1.stderr}")

print(f"Running {script_path}...")
result1 = subprocess.run(["python", script_path, "-o", "-i", "-p","-f", file5_path], capture_output=True, text=True)
print(f"Output of {script_path}:\n{result1.stdout}")
if result1.stderr:
    print(f"Errors from {script_path}:\n{result1.stderr}")

print("\nAll scripts executed.")