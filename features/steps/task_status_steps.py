from behave import given, when, then
from data.task import TaskEntry


@given('the following mock task entries exist')
def step_impl(context):
    for row in context.table:
        task_id = row['task_id']
        status = row['status']


@when('I request the status of task "{task_id}"')
def step_impl(context, task_id):
    # Send a request to the /task_status endpoint
    response = context.client.get(f'/vector_store/task_status/{task_id}')
    context.response = response

@given('I do not have valid permissions')
def step_impl(context):
    # Simulate lack of permissions (this can be handled in your app logic)
    token = 'invalid_token'

@then('the response status should be {status_code:d}')
def step_impl(context, status_code):
    assert context.response.status_code == status_code

@then('the response should contain "{key}" as "{value}"')
def step_impl(context, key, value):
    #response_json = context.response.get_json()
    #assert response_json.get(key) == value
    assert context.response.json()['data'][key] == value
