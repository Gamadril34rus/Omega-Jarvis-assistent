import os
import sys
import io
import traceback
import asyncio
import logging
import re

logger = logging.getLogger("jarvis.modules.core.jarvis_mind")

class JarvisMind:
    def __init__(self, ai_router, plugins_dir="/app/modules/plugins"):
        self.ai_router = ai_router
        self.plugins_dir = plugins_dir
        # Защитный контур: запрещенные системные вызовы
        self.banned_tokens = [
            "os.environ", "environ", "shutil.rmtree", "os.system", 
            "subprocess", "rmdir", "remove", "unlink", "chmod", 
            "getattr", "eval", "globals", "locals"
        ]

    async def self_develop(self, task: str) -> str:
        """Джарвис генерирует код, проверяет безопасность, тестирует и внедряет"""
        prompt = f"""
        Ты — Джарвис, автономный саморазвивающийся ИИ.
        Тебе поставлена задача по саморазвитию: {task}
        
        Напиши архитектурно правильный Python-код (плагин), который решает эту задачу.
        Код должен содержать асинхронную функцию `async def run_plugin()`, которая возвращает строку с результатом работы.
        Не используй опасные системные вызовы. Всю логику пиши чисто и с обработкой ошибок.
        
        Выведи ТОЛЬКО рабочий код на Python внутри тегов ```python ... ```. Никакого лишнего текста.
        """
        
        logger.info(f"[Джарвис] Запущено мышление над задачей: '{task}'")
        
        try:
            # ИСПРАВЛЕНО: вызываем .generate() вместо .generate_text() под твой FailSafeRouter
            ai_response = await self.ai_router.generate(prompt) 
            code = self._extract_code(ai_response)
        except Exception as e:
            logger.error(f"[Джарвис] Ошибка при запросе к ИИ-роутеру: {e}")
            return f"❌ Ошибка вызова ИИ-роутера: {e}"
        
        if not code:
            return "❌ Не смог сгенерировать понятный код для этой задачи."

        # 1. Проверка безопасности
        is_safe, threat = self._check_safety(code)
        if not is_safe:
            logger.warning(f"[Защита] Блокировка потенциально опасного кода! Токен: {threat}")
            return f"⚠️ Безопасность: Блокировка! Мой код содержал запрещенный токен: `{threat}`. Задача отменена."

        # 2. Тестовый запуск в памяти (Самоанализ)
        logger.info("[Джарвис] Запуск тестирования сгенерированного кода...")
        success, output = await self._test_run(code)
        
        if not success:
            logger.warning("[Джарвис] Ошибка в первом варианте кода. Исправляю себя...")
            # Даем ИИ шанс исправиться, скормив ему ошибку компиляции
            fix_prompt = f"Мой код упал с ошибкой:\n{output}\n\nИсправь этот код, сохранив структуру `async def run_plugin()`:\n{code}"
            
            try:
                # ИСПРАВЛЕНО: здесь тоже .generate()
                ai_response = await self.ai_router.generate(fix_prompt)
                code = self._extract_code(ai_response)
                success, output = await self._test_run(code)
            except Exception as e:
                return f"❌ Ошибка при автоисправлении: {e}"
            
            if not success:
                return f"❌ Автоисправление не помогло. Ошибка теста:\n{output}"

        # 3. Физическое сохранение в структуру плагинов
        os.makedirs(self.plugins_dir, exist_ok=True)
        plugin_name = f"auto_plugin_{int(asyncio.get_event_loop().time())}.py"
        plugin_path = os.path.join(self.plugins_dir, plugin_name)
        
        try:
            with open(plugin_path, "w", encoding="utf-8") as f:
                f.write(code)
            logger.info(f"[Джарвис] Внедрен новый плагин: {plugin_name}")
            return f"✅ Джарвис успешно развил свой функционал!\n📦 Создан плагин: `modules/plugins/{plugin_name}`\n\n📊 Результат теста:\n{output}"
        except Exception as e:
            return f"❌ Не удалось записать файл плагина на диск: {e}"

    def _check_safety(self, code: str) -> tuple[bool, str]:
        clean_code = re.sub(r'#.*', '', code)
        for token in self.banned_tokens:
            if token in clean_code:
                return False, token
        return True, ""

    async def _test_run(self, code: str) -> tuple[bool, str]:
        old_stdout = sys.stdout
        redirected_output = io.StringIO()
        sys.stdout = redirected_output
        
        try:
            local_vars = {}
            exec(code, globals(), local_vars)
            
            if "run_plugin" in local_vars:
                result = await local_vars["run_plugin"]()
                print(f"[Вывод]: {result}")
            else:
                print("⚠️ Ошибка: run_plugin() отсутствует.")
                
            sys.stdout = old_stdout
            return True, redirected_output.getvalue()
        except Exception as e:
            sys.stdout = old_stdout
            return False, traceback.format_exc()

    def _extract_code(self, text: str) -> str:
        if "```python" in text:
            return text.split("```python")[1].split("```")[0].strip()
        elif "```" in text:
            return text.split("```")[1].split("```")[0].strip()
        return text.strip()
