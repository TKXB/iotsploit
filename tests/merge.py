import os

# 定义需要合并的目录
directory = '/home/tkxb/HDD/Projects/zeekr_sat_main-master'  # 将 'your_directory_path' 替换为目标目录

# 定义输出文件名
output_file = 'merged_output.py'

# 定义要排除的目录列表
exclude_dirs = ['env', 'nogotofail-1.2.0_chennan_2to3']

def should_exclude(file_path):
    for exclude_dir in exclude_dirs:
        if exclude_dir in file_path:
            return True
    return False

# 打开输出文件
with open(output_file, 'w', encoding='utf-8') as outfile:
    # 遍历目录下的所有文件
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                full_path = os.path.join(root, file)
                # 检查文件路径是否包含任何排除目录
                if should_exclude(full_path):
                    continue
                # 写入文件路径和文件名
                outfile.write(f'# File: {full_path}\n')
                # 读取并写入文件内容
                with open(full_path, 'r', encoding='utf-8') as infile:
                    outfile.write(infile.read())
                    outfile.write('\n\n')

print(f'All Python files (excluding specified directories) have been merged into {output_file}')
