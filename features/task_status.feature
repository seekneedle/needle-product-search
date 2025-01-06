Feature: Task Status Retrieval

  Background:
    Given the following mock task entries exist:
      | task_id                               | status    |
      | 123e4567-e89b-12d3-a456-426614174000 | RUNNING   |
      | 123e4567-e89b-12d3-a456-426614174001 | SUCCESS   |
      | 123e4567-e89b-12d3-a456-426614174002 | FAIL      |

  Scenario: Retrieve status of a running task
    When I request the status of task "123e4567-e89b-12d3-a456-426614174000"
    Then the response status should be 200
    And the response should contain "status" as "RUNNING"

  Scenario: Retrieve status of a successful task
    When I request the status of task "123e4567-e89b-12d3-a456-426614174001"
    Then the response status should be 200
    And the response should contain "status" as "SUCCESS"

  Scenario: Retrieve status of a failed task
    When I request the status of task "123e4567-e89b-12d3-a456-426614174002"
    Then the response status should be 200
    And the response should contain "status" as "FAIL"

  Scenario: Attempt to retrieve status of a non-existent task
    When I request the status of task "123e4567-e89b-12d3-a456-426614174004"
    Then the response status should be 404
    And the response should contain "detail" as "Task not found."

  Scenario: Attempt to retrieve status without valid permissions
    Given I do not have valid permissions
    When I request the status of task "123e4567-e89b-12d3-a456-426614174000"
    Then the response status should be 401
    And the response should contain "detail" as "Invalid permission."

  Scenario: Attempt to retrieve status with an invalid task_id format
    When I request the status of task "invalid_task_id"
    Then the response status should be 404
    And the response should contain "detail" as "Task not found."

  Scenario: Retrieve status of a task with an empty task_id
    When I request the status of task ""
    Then the response status should be 404
    And the response should contain "detail" as "Task not found."
