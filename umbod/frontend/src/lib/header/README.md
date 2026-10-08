# Account identity

`accountIdentity.ts` validates the current-user response and maps it to header presentation state. The response requires a string subject, name, and an explicit string-or-null email; omitted emails are not accepted. Null email keeps the identity visible while account components hide only the email row. Picture handling and hidden subject preservation are unchanged.

Authentication and administrator membership remain API responsibilities. The admin layout preserves actual 401 and 403 failures rather than treating unavailable profile data as authentication failure. Deploy the nullable API contract with a rebuilt frontend; older frontend builds require a string email.
