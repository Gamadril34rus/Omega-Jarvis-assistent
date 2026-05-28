            try:
                logger.info("Переход на страницу авторизации Advego...")
                await page.goto("https://advego.com/login/", timeout=60000)
                
                # Ожидаем, пока прекратится активный сетевой обмен
                await page.wait_for_load_state("networkidle")
                
                # Ждем появления формы авторизации
                try:
                    await page.wait_for_selector('form[action*="login"]', timeout=10000)
                except Exception:
                    logger.warning("[Advego] Форма входа не найдена по селектору формы. Проверяем вкладку 'Вход'...")
                    login_tab = await page.query_selector('text="Вход"')
                    if login_tab and await login_tab.is_visible():
                        await login_tab.click()
                        await asyncio.sleep(2)

                # Локализуем конкретную форму авторизации, чтобы не цеплять поля регистрации
                login_form = page.locator('form[action*="login"], #host_login_form, .blocks-container').first
                
                # Ищем поле для логина внутри этой формы
                login_input = login_form.locator('input[name="login"], input[name="email"]').filter(has_not=page.locator('[style*="display: none"]'))
                await login_input.first.click()
                await login_input.first.fill(self._login)
                await asyncio.sleep(0.5)
                
                # Ищем поле пароля строго внутри этой же формы
                password_input = login_form.locator('input[name="password"]').filter(has_not=page.locator('[style*="display: none"]'))
                await password_input.first.click()
                await password_input.first.fill(self._password)
                await asyncio.sleep(0.5)
                
                # Ищем кнопку отправки внутри этой формы
                submit_button = login_form.locator('button[type="submit"], input[type="submit"], .btn_orange').first
                await submit_button.click()
                
                logger.info("Ожидание завершения авторизации...")
                try:
                    await page.wait_for_url("https://advego.com/", timeout=15000)
                except Exception:
                    await asyncio.sleep(5) 

                logger.info("Переход на страницу поиска заказов...")
                await page.goto("https://advego.com/job/find/?job_type=1&job_type=2", timeout=60000)
                
                try:
                    await page.wait_for_selector('.job_item', timeout=10000)
                except Exception:
                    logger.info("На странице нет доступных карточек заказов.")
                    return "Заказов пока нет", 0.0
                
                job_card = await page.query_selector('.job_item')
                if not job_card:
                    return "Заказов пока нет", 0.0

                take_button = await job_card.query_selector('a.job_take_link')
                if take_button:
                    await take_button.click()
                    logger.info("Кнопка 'Взять в работу' успешно нажата!")
                    return "Заказ успешно взят в работу!", 150.0 
                
                return "Доступны только тендеры, ждем свободный заказ", 0.0
