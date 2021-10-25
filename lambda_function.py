from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from selenium import webdriver
from selenium.common import exceptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from time import sleep
import boto3
import base64
import datetime
import json
import logging
import os
import sys


def wait_for(xpath: str):
    logging.info(f'waiting for {xpath}')
    try:
        WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, xpath)))
    except Exception as e:
        logging.info(f'reached webdriver wait timeout {e}')
    return True

def create_multipart_message(
        sender: str, recipients: list, title: str, text: str=None, html: str=None, attachments: list=None)\
        -> MIMEMultipart:
    """
    Creates a MIME multipart message object.
    Uses only the Python `email` standard library.
    Emails, both sender and recipients, can be just the email string or have the format 'The Name <the_email@host.com>'.

    :param sender: The sender.
    :param recipients: List of recipients. Needs to be a list, even if only one recipient.
    :param title: The title of the email.
    :param text: The text version of the email body (optional).
    :param html: The html version of the email body (optional).
    :param attachments: List of files to attach in the email.
    :return: A `MIMEMultipart` to be used to send the email.
    """
    multipart_content_subtype = 'alternative' if text and html else 'mixed'
    msg = MIMEMultipart(multipart_content_subtype)
    msg['Subject'] = title
    msg['From'] = sender
    msg['To'] = ', '.join(recipients)

    # Record the MIME types of both parts - text/plain and text/html.
    # According to RFC 2046, the last part of a multipart message, in this case the HTML message, is best and preferred.
    if text:
        part = MIMEText(text, 'plain')
        msg.attach(part)
    if html:
        part = MIMEText(html, 'html')
        msg.attach(part)

    # Add attachments
    for attachment in attachments or []:
        with open(attachment, 'rb') as f:
            part = MIMEApplication(f.read())
            part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(attachment))
            msg.attach(part)

    return msg


def send_mail(
        sender: str, recipients: list, title: str, text: str=None, html: str=None, attachments: list=None) -> dict:
    """
    Send email to recipients. Sends one mail to all recipients.
    The sender needs to be a verified email in SES.
    """
    msg = create_multipart_message(sender, recipients, title, text, html, attachments)
    ses_client = boto3.client('ses')  # Use your settings here
    return ses_client.send_raw_email(
        Source=sender,
        Destinations=recipients,
        RawMessage={'Data': msg.as_string()}
    )


def lambda_handler(event, context):
    sm_client = boto3.client(service_name='secretsmanager')
    secret_name = "CHANGE_ME" # AWS Secret manager secret
    device_farm_project_arn = "CHANGE_ME" # devicefarm project arn, starts with: arn:aws:devicefarm:us-west-2:
    get_secret_value_response = sm_client.get_secret_value(SecretId=secret_name)
    secret = json.loads(get_secret_value_response['SecretString'])

    devicefarm = boto3.client('devicefarm', region_name='us-west-2')
    remote_url = devicefarm.create_test_grid_url(
    projectArn=device_farm_project_arn, expiresInSeconds=300)['url'] 

    logging.info("Creating a new session with remote URL: " + remote_url)
    driver = webdriver.Remote(command_executor=remote_url, desired_capabilities=DesiredCapabilities.CHROME)
    logging.info("Created the remote webdriver session: " + driver.session_id)

    logging.info('opening ordernet page')
    driver.maximize_window()
    driver.get("https://meitav.ordernet.co.il/")
    sleep(8)
    logging.info('type username')
    username_box = '//*[@id="login_form"]/fieldset/div[1]/input'
    wait_for(username_box)
    username_button = driver.find_element_by_xpath(username_box)
    username_button.click()
    username_button.send_keys(secret['username'])
    logging.info('type password')
    password_box = '//*[@id="password"]'
    wait_for(password_box)
    password_button = driver.find_element_by_xpath(password_box)
    password_button.click()
    password_button.send_keys(secret['passwrord'])
    sleep(0.2)
    logging.info('click on login button')
    login_xpath = '//*[@id="login_form"]/fieldset/div[3]'
    wait_for(login_xpath)
    login_button = driver.find_element_by_xpath(login_xpath)
    login_button.click()
    logging.info('click on auth button')
    auth_xpath = '//*[@id="scxBody"]/div[5]/div/div/div/div[2]/div[2]/div[6]/button'
    wait_for(auth_xpath)
    sleep(16)
    auth_button = driver.find_element_by_xpath(auth_xpath).click()
    sleep(6)
    driver.save_screenshot('/tmp/screen1.png')

    logging.info("Teardown the remote webdriver session: " + driver.session_id)
    driver.quit()
    
    
    # send email
    sender_ = 'Name <email@address.com>' # replace that with SES email address
    recipients_ = ['type.your@email.com']
    title_ = 'Your daily screenshot from Ordernet is here'
    text_ = 'Here is the screenshot'
    body_ = """<html><head></head><body><h1>End of day trading</h1><br>."""
    attachments_ = ['/tmp/screen1.png']

    response_ = send_mail(sender_, recipients_, title_, text_, body_, attachments_)
    print(response_)
