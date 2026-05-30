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
        # Защитный контур: блокируем деструктивные вызовы
        self.banned_tokens = [
            "os.environ", "environ", "shutil.rmtree", "os.system", 
            "subprocess", "rmdir", "remove", "unlink", "chmod", 
            "getattr", "eval", "globals", "locals"
        ]

    async def self_develop(self, task: str) -> str:
        """Цикл автономной генерации, проверки, исправления и внедрения кода"""
        prompt = f"""
        Ты — Джарвис, автономное саморазвивающееся ядро ИИ.
        Твоя задача: {task}
        
        ТРЕБОВАНИЯ К КОДУ:
        1. Напиши архитектурно правильный, чистый код на Python.
        2. Твой код ОБЯЗАТЕЛЬНО должен содержать асинхронную функцию:
           async def run_plugin() -> str:
               # Логика работы плагина
               return "Результат работы в виде строки"
        3. Название функции `run_plugin` изменять НЕЛЬЗЯ! Это точка входа.
        4. Используй только предустановленные библиотеки: `playwright` (async_api), `asyncio`, `logging`, `json`, `re`, `sys`, `os`.
        5. Использование `selenium` КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО! В системе установлен только Playwright.
        6. Всю логику оборачивай в try/except для предотвращения падений.
        
        Выведи ТОЛЬКО рабочий код внутри разметки ```python ... ```. Никакого лишнего текста вне блока кода.
        """
        
        logger.info(f"[Джарвис] Запущено мышление над задачей: '{task}'")
        
        try:
            # Запрос к FailSafeRouter через метод .complete()
            messages = [{"role": "user", "content": prompt}]
            ai_response = await self.ai_router.complete(messages) 
            code = self._extract_code(ai_response)
        except Exception as e:
            logger.error(f"[Джарвис] Ошибка при запросе к ИИ-роутеру: {e}")
            return f"❌ Ошибка вызова ИИ-роутера: {e}"
        
        if not code:
            return "❌ Не смог сгенерировать понятный код для этой задачи."

        # 1. Защитный барьер безопасности
        is_safe, threat = self._check_safety(code)
        if not is_safe:
            logger.warning(f"[Защита] Блокировка потенциально опасного кода! Токен: {threat}")
            return f"⚠️ Безопасность: Блокировка! Мой код содержал запрещенный токен: `{threat}`. Задача отменена."

        # 2. Тестирование компиляции и вызова в памяти (Самоанализ)
        logger.info("[Джарвис] Запуск тестирования сгенерированного кода...")
        success, output = await self._test_run(code)
        
        if not success or "run_plugin() отсутствует" in output:
            logger.warning("[Джарвис] Ошибка компиляции или структуры. Запуск автоисправления...")
            
            error_details = output if output else "Отсутствует обязательная функция async def run_plugin()"
            fix_prompt = f"""
            Мой сгенерированный код не прошел автоматический тест.
            Ошибка компиляции/структуры:
            {error_details}
            
            Пожалуйста, исправь этот код. 
            Убедись, что в коде ПРИСУТСТВУЕТ функция `async def run_plugin()`, которая возвращает строку, и код использует исключительно Playwright (без selenium!).
            
            Предыдущий код:
            {code}
            """
            
            try:
                fix_messages = [{"role": "user", "content": fix_prompt}]
                ai_response = await self.ai_router.complete(fix_messages)
                code = self._extract_code(ai_response)
                success, output = await self._test_run(code)
            except Exception as e:
                return f"❌ Ошибка при автоисправлении: {e}"
            
            if not success:
                return f"❌ Автоисправление не помогло. Код нестабилен. Ошибка теста:\n{output}"

        # 3. Физическая запись на диск
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
                # Безопасный асинхронный вызов с таймаутом, чтобы не зависнуть на бесконечных циклах
                result = await asyncio.wait_for(local_vars["run_plugin"](), timeout=15.0)
                print(f"[Вывод плагина]: {result}")
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