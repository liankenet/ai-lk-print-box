# 使用Python 3.13官方镜像
FROM python:3.13-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装uv包管理器
RUN pip install uv

# 复制项目文件
COPY pyproject.toml uv.lock ./
COPY lianke_printing/ ./lianke_printing/
COPY main.py ./
COPY SKILL.md ./

# 安装Python依赖
RUN uv sync --frozen

# 暴露端口（如果需要的话）
EXPOSE 8000

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 创建非root用户
RUN useradd --create-home --shell /bin/bash app
RUN chown -R app:app /app
USER app

# 启动命令
CMD ["uv", "run", "main.py"]
