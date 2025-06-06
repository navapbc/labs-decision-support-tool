# Promptfoo evaluations

We use [Promptfoo](https://promptfoo.dev) to automatically evaluate the chatbot's performance on prepared test inputs. Nava team members can create Google Sheets and run the chatbot against them using GitHub actions.

## How to run evaluations against a Google Sheet

1. Create a new Google Sheet ([sheets.new](https://sheets.new)) 
1. Create three columns: `capability`, `question`, and `__expected`.
    - `capability` should describe what you'd like to test, e.g., "It refuses to answer out of scope questions"
    - `question` is the input that will be sent to the chatbot, e.g., "How do I apply for PFML in Massachusetts?"
    - `__expected` is the assertion used to access the chatbot's output, e.g., `contains:Sorry, I can't answer that.`
See [this sheet for a minimal example](https://docs.google.com/spreadsheets/d/1xpOBO7FnRgmgILYwn0gj_LGqqdpi-E5cfQxdgscw21s/edit?gid=0#gid=0). There are many other types of assertions in addition to `contains:`: Promptfoo's documentation has a [list of assertion types](https://www.promptfoo.dev/docs/configuration/expected-outputs/#assertion-types). Its documentation also has [additional details about the promptfoo sheet format](https://www.promptfoo.dev/docs/configuration/parameters/#import-from-csv) if you're interested or need additional functionality.
1. Share **edit access** to the sheet with `navalabs-promptfoo@navalabs-promptfoo.iam.gserviceaccount.com`.
1. Copy the URL of the Google Sheet you've created, e.g., `https://docs.google.com/spreadsheets/d/1xpOBO7FnRgmgILYwn0gj_LGqqdpi-E5cfQxdgscw21s/edit?gid=0#gid=0`
1. Go to the [Prompt Evaluation GitHub action](https://github.com/navapbc/labs-decision-support-tool/actions/workflows/promptfoo-googlesheet-evaluation.yml).
1. Click "Run workflow":
![Run workflow button in GitHub Actions](promptfoo-evaluations-run-workflow.png)
1. Paste in the Google Sheet URL into both the  `Google Sheet URL for test case inputs` and `Google Sheet URL for evaluation outputs` fields.
    - Leave `Use workflow from` and `Chatbot API endpoint URL` set to their defaults. Additional detail about these is below in Advanced Usage.
    - If there is a non-zero `gid` at the end of the URL for your `Google Sheet URL for evaluation outputs`, that tab within your Google Sheet will be **overwritten**. To prevent this, edit it out of the URL, e.g., converting `https://docs.google.com/spreadsheets/d/1xpOBO7FnRgmgILYwn0gj_LGqqdpi-E5cfQxdgscw21s/edit?gid=1234#gid=12345` to `https://docs.google.com/spreadsheets/d/1xpOBO7FnRgmgILYwn0gj_LGqqdpi-E5cfQxdgscw21s/edit`.
1. Click `Run workflow`. The page will refresh in a few seconds or you can refresh manually. Once refreshed, you should see your workflow in the list with a yellow icon indicating that it's running: 
![Example list of running workflows](promptfoo-evaluation-running-workflows.png)
1. After about three to five minutes, the workflow should finish running (indicated by a green checkmark icon). The results of your evaluation will be in the Google Sheet.

## Advanced usage

### Run workflow from

You can change the `Run workflow from` dropdown to select a branch that GitHub will use for executing the action. If you are not certain that you need to adjust this setting, you should leave it set to `main`. Note that changing this option only changes the branch that the workflow .yaml is run from. It does not change the code (e.g., prompt) of the chatbot that is evaluated.

### Chatbot API endpoint URL

By default, the version of the chatbot that is evaluated is our DEV instance. You can manually change this to, for example, evaluate a different version of the chatbot's prompt in a preview environment, e.g., `http://p-310-app-dev-652842717.us-east-1.elb.amazonaws.com/api/query` (without SSL since the certificate will fail due to having a different domain name).
