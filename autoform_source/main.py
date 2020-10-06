'''
Automatic Google Form Bot
by thisismy-github, 8/21/2020
'''

import os, time, threading
import PySimpleGUI as pgui
import requests
from requestium import Session, Keys
from bin.configparsebetter import ConfigParseBetter
from bin.systray.traybar import SysTrayIcon


def get_formatted_form_url(url):    # Formats form URL to ensure it ends with "/formResponse"
    if url:
        if 'forms.gle/' in url: # detect and correct shortened links
            url = requests.get(url).url
        if '?' in url:
            url = url[:url.find('?')]   # cut out everything past the "?"
        urlparts = url.split('/')       # split string into list
        urlparts[-1] = 'formResponse'   # replace end of url with "formResponse"
        url = '/'.join(urlparts)        # rejoins list into string
    return url


cfg = ConfigParseBetter('autoform.ini')     # Reads and loads config file
cfg.setSection('LOGIN')
cfg.load('email')
cfg.load('password')
cfg.setSection('SETTINGS')
cfg.load('form_url')
cfg.form_url = get_formatted_form_url(cfg.form_url)
cfg.load('form_check_interval', 20)
cfg.load('delay_after_form_submitted', 90)
cfg.load('page_load_max_wait_time', 15)
cfg.load('auto_select_answers', False)
cfg.possible_answers = cfg.load('possible_answers', '1,option 1').lower().split(',')
cfg.load('theme', 'Default 1')
cfg.write()


def save_config(values):    # Saves GUI values back to config file and returns URL
    global cfg
    print('Saving config with values:', values)
    url = get_formatted_form_url(values['url'])
    cfg.saveTo('LOGIN', 'email', values['email'])
    cfg.saveTo('LOGIN', 'password', values['password'])
    cfg.saveTo('SETTINGS', 'form_url', url)
    cfg.write()
    return cfg.form_url


class GoogleFormAutoFiller:
    def __init__(self, session):
        print('Initializing...')
        self.url = cfg.form_url
        self.session = session
        self.values = None
        self.last_entries = None
        self.check_attendance = False
        self.attendance_thread = None
        self.gui_running = True
        self.logged_in = False


    def start(self):    # Initializes GUI and system tray icon, then starts the event loop.
        pgui.theme(cfg.theme)
        font = None
        layout = [
            [pgui.Text('Email   ', size=(8,1), font=font), pgui.Input(cfg.email, key='email', size=(35,1))],
            [pgui.Text('Password', size=(8,1), font=font), pgui.Input(cfg.password, key='password', password_char='*', size=(35,1))],
            [pgui.Text('Form URL', size=(8,1), font=font), pgui.Input(cfg.form_url, key='url', size=(35,1))],
            [pgui.Text('Not logged in yet', justification='center', size=(41,2), text_color='red', key='login_status')],
            [
                pgui.Button('Exit', size=(7,1), font=font),
                pgui.Button('Minimize To System Tray', size=(22,1), font=font),
                pgui.Button('Login', size=(7,1), font=font)
            ]
        ]
        self.window = pgui.Window('Attendence Form Autofill', layout, icon='.\\bin\\gform.ico')
        self.createSystemTrayIcon()
        while self.gui_running:
            event, values = self.window.read()
            if values is not None: self.values = values
            if event in (pgui.WIN_CLOSED, 'Exit', None):
                save_config(self.values)
                self.shutdown()
                break
            elif event == 'Minimize To System Tray':
                self.window.Hide()
                self.systray.start()
            elif event == 'Login':
                self.url = get_formatted_form_url(self.values['url'])
                save_config(self.values)
                if not self.logged_in:
                    self.attendance_thread = threading.Thread(target=self.wait_for_attendence, daemon=True)
                    self.attendance_thread.start()
                    self.login()
        if self.gui_running: self.shutdown()


    def shutdown(self, *args): # Close everything before ending program
        if not self.gui_running: return
        try:
            print('Exiting...')
            self.gui_running = False
            self.check_attendance = False
            self.window.close()
            threading.Thread(target=self.systray.shutdown, daemon=True).start()
            os.system('taskkill /im chromedriver.exe /f /t')    # force close chromedriver
            exit(0)
        except Exception as error:
            print(type(error), error)


    def createSystemTrayIcon(self): # Creates a system tray icon to use with our GUI
        self.systray = SysTrayIcon(
            icon='.\\bin\\gform.ico',
            hover_text='Attendence Form Autofill',
            menu_options=(('Open', None, self.unhideGUI),),
            on_quit=self.shutdown
        )
        self.systray.start()


    def unhideGUI(self, *args): # Reveals GUI after it's been minimized to system tray
        self.window.UnHide()


    def wait_for_attendence(self):
        '''
        Periodically checks the desired form. If the form is open and accepting
        responses, it attempts to fill out questions and submit a response.
        '''
        print('Form-checking thread opened.')
        while self.gui_running:
            while self.check_attendance:
                startTime = time.time()
                delay = cfg.form_check_interval

                print('\nChecking form at url:', self.url)
                self.response = self.session.get(self.url)

                if 'formrestricted' in self.response.url:
                    self.session.quit()
                    print('Invalid profile used to login. Please verify your username and password and restart.')
                    self.window['login_status'].update('Login attempt failed, this form cannot be accessed.', text_color='red')
                elif 'closedform' in self.response.url:
                    currTime = time.strftime('%I:%M:%S%p',time.localtime()).lstrip('0').lower()
                    print('Form detected as closed at', currTime)
                    self.window['login_status'].update('Form detected as closed at {}'.format(currTime), text_color='green')
                elif 'alreadyresponded' in self.response.url:
                    currTime = time.strftime('%I:%M:%S%p',time.localtime()).lstrip('0').lower()
                    print('Form detected as already answered at', currTime)
                    self.window['login_status'].update('Form detected as already answered at {}'.format(currTime), text_color='green')
                else:
                    print('Attempting to send response to:', self.response.url)
                    self.window['login_status'].update('Attempting to send response', text_color='green')
                    currTime = time.strftime('%I:%M:%S%p',time.localtime()).lstrip('0').lower()
                    try:
                        self.send_answers(*self.get_entries(self.response.text))                     # NOTE: ANSWERS SENT HERE
                        # If entries were detected, the response must have been successful. To avoid extra coding work, empty
                        # forms return a fake dictionary with a dummy entry so that the response is detected as successful.
                        if self.last_entries:
                            print('Response submitted at', currTime)
                            self.window['login_status'].update('Response submitted at {}'.format(currTime), text_color='green')
                            delay = cfg.delay_after_form_submitted
                        else:
                            print('Response attempt failed at', currTime)
                            self.window['login_status'].update('Response attempt failed at {}'.format(currTime), text_color='orange')
                    except:
                        print('Response attempt failed at', currTime)
                        self.window['login_status'].update('Response attempt failed at {}'.format(currTime), text_color='orange')
                responseTime = time.time()-startTime
                time.sleep(delay-(responseTime if responseTime <= delay else 0))


    def login(self):
        '''
        Logs into Google through an external site using Selenium, then transfers
        cookies to requests library for accessing google form. Attempting to login to
        Google directly will give errors saying our browser isn't secure. Partially taken
        from: https://stackoverflow.com/questions/60117232/selenium-google-login-block
        '''
        try: self.session.driver.get('https://stackoverflow.com/users/signup?ssrc=head&returnurl=%2fusers%2fstory%2fcurrent%27')
        except Exception as error:
            print(type(error), error)
            e = str(error)
            driverVersion = e.replace('Message: session not created: This version of ChromeDriver only supports Chrome version ', '').split()[0]
            browserVersion = e[e.find('\n'):e.find(' with binary path')]
            self.window['login_status'].update('FATAL ERROR: Current ChromeDriver version is {}{}'.format(driverVersion, browserVersion), text_color='red')
            os.system('taskkill /im chromedriver.exe /f /t')    # force close chromedriver
            return
        self.session.driver.ensure_element_by_xpath('//*[@id="openid-buttons"]/button[1]', 'visible').click()
        self.session.driver.ensure_element_by_xpath('//input[@type="email"]', 'visible').send_keys(self.values['email'])
        self.session.driver.ensure_element_by_xpath('//*[@id="identifierNext"]', 'visible').click()
        self.session.driver.ensure_element_by_xpath('//input[@type="password"]', 'visible').send_keys(self.values['password'])
        self.session.driver.ensure_element_by_xpath('//*[@id="passwordNext"]', 'visible').click()
        time.sleep(2)   # pause to let previous click go through
        print('SESSION DRIVER GET:',self.url)
        self.session.driver.get(self.url)

        self.session.transfer_driver_cookies_to_session()
        self.saved_cookies = self.session.driver.get_cookies()  # Save cookies for later
        self.session.driver.close()     # Close browser window

        self.logged_in = True
        self.check_attendance = True    # Start checking the actual form

        print('Ready to check the form.')
        self.window['login_status'].update('Logged in and active', text_color='green')



    def get_options(self, r, startIndex, endIndex, entryType='_sentinel'):
        '''
        Gets list of options (possible answers) from an entry (question) on a Google Form.
        NOTE: This version ONLY works for multiple-choice, checkboxes, and dropdowns.
        '''
        print('Getting options...')
        options = []
        if endIndex == -1:
            endIndex = len(r)
        if entryType == '_sentinel':
            optionID = 'data-value'

        optionIndex = r.find(optionID, startIndex) + 12
        while optionIndex - 12 != -1 and optionIndex <= endIndex:
            optionName = r[optionIndex:r.find('"', optionIndex)]
            options.append(optionName)
            optionIndex = r.find(optionID, optionIndex+1) + 12
        return options


    def get_entries(self, r):
        '''
        Gets dictionary of entries (questions) and their options (answers). This
        is done by parsing a POST request sent to the form. Entries are determined by
        finding elements starting with "entry." Options are determined by finding all
        elements between two entries containing certain identifiers.
        '''
        print('Getting entries...')
        entries = {}

        # Checks if form is empty or not
        entryCountIndex = r.find('data-last-entry') + 17
        if entryCountIndex - 17 != -1:
            try:
                entryCount = int(r[entryCountIndex:r.find('"', entryCountIndex)])
                if entryCount == 0:
                    print('Empty form detected. Using Selenium to click submit...')
                    self.last_entries = {0:0}   # fake dictionary, see "if self.last_entries" in wait_for_attendance for details
                    return {}, True     # return empty entries dict and True for force_selenium
            except:
                pass

        entryIndex = r.find('entry.')
        while entryIndex != -1:     # loop until no more entries are found
            lastIndex = entryIndex

            # Separate entry ID from entry suffix
            entry = r[entryIndex:r.find('"', lastIndex)].split('_')
            entryID = entry[0]

            #entries[entryID] = ''
            entryIndex = r.find('entry.', lastIndex+6)
            options = self.get_options(r, lastIndex, entryIndex, '_sentinel')
            print('Entry "{}" has the following options: {}'.format(entryID, options))
            print('Options matching these names will be picked: {}'.format(cfg.possible_answers))

            for option in options:  # loop through options to find which one to select
                if cfg.auto_select_answers:
                    if option:
                        # replace spaces in option with +'s because of google's formatting
                        entries[entryID] = option.replace(' ', '+')
                        break
                else:
                    if option and option.lower() in cfg.possible_answers:
                        entries[entryID] = option.replace(' ', '+')
                        break

        print('Returning entries...', entries)
        self.last_entries = entries
        return entries, False


    def send_answers(self, entries, force_selenium=False):
        '''
        Attempts to submit response to form through a POST. If a warning
        appears, we must resort to Selenium to click the button for us.
        '''
        print('Sending answers:', entries)
        url = get_formatted_form_url(self.values['url'])
        url = url if url else self.url
        url = self.values['url'] + '?'
        for entry, value in entries.items():
            url += '{}={}&'.format(entry, value)
        url = url.rstrip('&')

        # Double-checks that the url is using formResponse and not viewform
        urlPieces = url.split('?')
        urlPieces[0] = urlPieces[0].replace('viewform', 'formResponse')
        url = '&'.join(urlPieces)
        url = url.replace('&', '?', 1)  # make sure there's only one '?' in the url
        print('Entries have been converted into the following url:\n   ',url)

        # this is done separately to avoid unneccesary POST request below
        if force_selenium:
            self.send_answers_selenium(url)

        # POST's and checks if a warning came up
        response = self.session.post(url)
        if 'You can only respond to this form once. Continue?' in response.text:
            self.send_answers_selenium(url)


    def send_answers_selenium(self, url):
        '''
        Opens form in Selenium, and manually clicks the submit button.
        First, it has to re-add all the cookies from before, though.
        '''
        print('Warning appeared, using Selenium to click submit.')
        self.session = Session('./bin/chromedriver', browser='chrome', default_timeout=cfg.page_load_max_wait_time)
        try: self.session.driver.get('https://stackoverflow.com/users/signup?ssrc=head&returnurl=%2fusers%2fstory%2fcurrent%27')
        except Exception as error:
            print(type(error), error)
            e = str(error)
            driverVersion = e.replace('Message: session not created: This version of ChromeDriver only supports Chrome version ', '').split()[0]
            browserVersion = e[e.find('\n'):e.find(' with binary path')]
            self.window['login_status'].update('FATAL ERROR: Current ChromeDriver version is {}{}'.format(driverVersion, browserVersion), text_color='red')
            os.system('taskkill /im chromedriver.exe /f /t')    # force close chromedriver
            return

        for cookie in self.saved_cookies:
            try: self.session.driver.ensure_add_cookie(cookie)
            except: pass
        print('Redirecting to form url...')

        self.session.driver.get(url)
        self.session.driver.ensure_element_by_css_selector('div.appsMaterialWizButtonPaperbuttonFilled', 'visible').click()
        time.sleep(0.5)
        self.session.transfer_driver_cookies_to_session()
        self.saved_cookies = self.session.driver.get_cookies()
        self.session.driver.close()



if __name__ == '__main__':
    attendenceBot = GoogleFormAutoFiller(Session('./bin/chromedriver',
                                                 browser='chrome',
                                                 default_timeout=cfg.page_load_max_wait_time))
    attendenceBot.start()