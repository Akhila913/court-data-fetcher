from django.shortcuts import render
from asgiref.sync import sync_to_async
from .models import QueryLog
from .scraper import fetch_case_details

# This is the key change: Wrap the synchronous ORM method to make it awaitable.
@sync_to_async
def log_query_to_db(case_type, case_number, case_year, result):
    """
    An async-safe function to create a QueryLog entry.
    """
    QueryLog.objects.create(
        case_type=case_type,
        case_number=case_number,
        case_year=case_year,
        raw_response=result.get('raw_html', ''),
        status=result.get('status'),
        error_message=result.get('message', '')
    )

async def search_view(request):
    """
    An async view to handle the form submission and scraping.
    """
    if request.method == 'POST':
        case_type = request.POST.get('case_type')
        case_number = request.POST.get('case_number')
        case_year = request.POST.get('case_year')

        # 1. Call the async scraper function and wait for its result.
        result = await fetch_case_details(case_type, case_number, case_year)

        # 2. Log the attempt to the database using the async-safe wrapper.
        await log_query_to_db(case_type, case_number, case_year, result)

        # 3. Render the appropriate template based on the result.
        if result['status'] == 'SUCCESS':
            return render(request, 'fetcher/results.html', {'data': result['data']})
        elif result['status'] == 'NO_DATA':
            return render(request, 'fetcher/error.html', {'message': result.get('message', 'No matching records found.')})
        else:
            # Show either the friendly no-data message or error message
            return render(request, 'fetcher/error.html', {'message': result.get('message', 'Unknown error')})


    # For GET requests, just show the initial search page.
    return render(request, 'fetcher/index.html')